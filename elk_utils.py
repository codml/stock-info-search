"""ELK-RAG 주식 검색 공통 모듈"""

import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from openai import OpenAI

load_dotenv()

INDEX_NAME = "stock_info"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
CHAT_MODEL = "gpt-4o-mini"
LEXICAL_SEARCH_FIELDS = ["회사명", "시장구분", "종목코드", "업종", "주요제품", "대표자명", "지역"]


def get_es_client():
    """Elasticsearch 클라이언트 반환"""
    return Elasticsearch("http://localhost:9200", http_compress=True)


def get_openai_client():
    """OpenAI 클라이언트 반환. API 키 미설정 시 ValueError 발생."""
    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        raise ValueError("AI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    return OpenAI(api_key=api_key)


def get_embedding(openai_client, text):
    """텍스트를 임베딩 벡터로 변환"""
    response = openai_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    return response.data[0].embedding


def get_index_mapping():
    """Elasticsearch 인덱스 매핑 정의 (dense_vector 포함)"""
    return {
        "properties": {
            "embedding": {
                "type": "dense_vector",
                "dims": EMBEDDING_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "업종": {"type": "text"},
            "주요제품": {"type": "text"},
        }
    }


def search_documents_semantic(es, openai_client, query, k=3, num_candidates=10):
    """시맨틱(knn) 검색으로 관련 주식 종목 반환"""
    query_embedding = get_embedding(openai_client, query)
    results = es.search(
        index=INDEX_NAME,
        knn={
            "field": "embedding",
            "query_vector": query_embedding,
            "k": k,
            "num_candidates": num_candidates,
        },
    )
    return [hit["_source"]["회사명"] for hit in results["hits"]["hits"]]


def search_documents_lexical(es, query, size=5):
    """렉시컬(multi_match) 검색으로 관련 주식 종목 반환"""
    results = es.search(
        index=INDEX_NAME,
        query={"multi_match": {"query": query, "fields": LEXICAL_SEARCH_FIELDS}},
        size=size,
        sort=[{"_score": {"order": "desc"}}],
    )
    return [hit["_source"]["회사명"] for hit in results["hits"]["hits"]]


def search_card_details(es, card_names):
    """회사명 목록으로 상세 정보 조회 (임베딩 필드 제외)"""
    result = es.search(
        index=INDEX_NAME,
        query={"terms": {"회사명.keyword": card_names}},
        source={"excludes": ["embedding"]},
    )
    return [hit["_source"] for hit in result["hits"]["hits"]]


def answer_question(es, openai_client, query, search_type="auto"):
    """주식 종목 RAG 기반 질문 답변. (답변, 관련회사목록, 검색유형) 튜플 반환."""
    query = query.strip()
    if not query:
        raise ValueError("질문을 입력해주세요.")

    if search_type == "auto":
        word_count = len(query.split())
        search_type = "semantic" if word_count >= 4 else "lexical"

    if search_type == "semantic":
        relevant_docs = search_documents_semantic(es, openai_client, query)
    else:
        relevant_docs = search_documents_lexical(es, query=query)

    if not relevant_docs:
        return "질문과 관련된 종목을 찾지 못했습니다. 검색어를 조금 더 구체적으로 입력해 주세요.", [], search_type

    context = "\n".join(relevant_docs)
    detail_info = search_card_details(es, relevant_docs)

    prompt = (
        f"[검색된 회사명]\n{context}\n\n"
        f"[회사 상세 정보]\n{detail_info}\n\n"
        f"[사용자 질문]\n{query}\n\n"
        "[답변 작성 지침]\n"
        "1) 질문 의도에 맞는 종목을 우선순위로 정리\n"
        "2) 근거는 제공된 상세 정보(업종/주요제품/시장구분/상장일 등)만 사용\n"
        "3) 정보가 없으면 추측하지 말고 '확인 불가'로 표기\n"
        "4) 한국어로 간결하게 작성"
    )
    response = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 한국 주식 종목 검색을 돕는 RAG 어시스턴트다. "
                    "반드시 검색된 문서 정보만 근거로 답하고, 사실이 불충분하면 불확실성을 명시하라. "
                    "재무/투자 조언을 단정적으로 하지 말고, 참고 정보라는 점을 짧게 덧붙여라."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    answer = response.choices[0].message.content
    return answer, relevant_docs, search_type
