from datetime import date, datetime
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elk_utils import (
    INDEX_NAME,
    LEXICAL_SEARCH_FIELDS,
    get_embedding,
    get_openai_client,
)

ES_HOST = "http://localhost:9200"
MARKET_SYNONYMS = {
    "코스피": ["코스피", "유가"],
    "유가": ["코스피", "유가"],
    "코스닥": ["코스닥"],
    "코넥스": ["코넥스"],
}

def get_client():
    """Elasticsearch 클라이언트 생성"""
    return Elasticsearch(ES_HOST, request_timeout=30)


def _to_date_string(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def search_index(index_name, field_name, match_name, max_results=100):
    """인덱스에서 필드 기반 검색 수행 (기존 호환용)"""
    client = get_client()
    fields = field_name if isinstance(field_name, list) else [field_name]
    s = Search(index=index_name).using(client)
    s = s.query("multi_match", fields=fields, query=match_name)
    s = s[:max_results]
    return s.execute()

def search_index_with_date_range(index_name, field_name, match_name, start_date, end_date, max_results=100):
    """날짜 범위와 함께 인덱스 검색 수행 (기존 호환용)"""
    client = get_client()
    fields = field_name if isinstance(field_name, list) else [field_name]
    s = Search(index=index_name).using(client)
    s = s.query("multi_match", fields=fields, query=match_name)
    s = s.filter("range", 상장일={"gte": _to_date_string(start_date), "lte": _to_date_string(end_date)})
    s = s[:max_results]
    return s.execute()


def search_stock_hybrid(
    index_name=None,
    semantic_query="",
    lexical_query="",
    market="",
    start_date=None,
    end_date=None,
    max_results=100,
):
    """
    주식 데이터 하이브리드 검색.
    - semantic: 업종/주요제품 임베딩 벡터(`embedding`) 기반 knn
    - lexical: 회사명/시장구분/종목코드/대표자명/지역/상장일 등
    """
    client = get_client()
    target_index = index_name or INDEX_NAME
    filters = []

    if market:
        market_values = MARKET_SYNONYMS.get(market, [market])
        if len(market_values) == 1:
            filters.append({"term": {"시장구분.keyword": market_values[0]}})
        else:
            filters.append({"terms": {"시장구분.keyword": market_values}})

    if start_date or end_date:
        range_cond = {}
        if start_date:
            range_cond["gte"] = _to_date_string(start_date)
        if end_date:
            range_cond["lte"] = _to_date_string(end_date)
        filters.append({"range": {"상장일": range_cond}})

    lexical_query = lexical_query.strip()
    semantic_query = semantic_query.strip()

    bool_query = {"filter": filters}
    if lexical_query:
        bool_query["must"] = [{"multi_match": {"query": lexical_query, "fields": LEXICAL_SEARCH_FIELDS}}]
    else:
        bool_query["must"] = [{"match_all": {}}]

    body = {
        "size": max_results,
        "query": {"bool": bool_query},
        "_source": {"excludes": ["embedding"]},
    }

    if semantic_query:
        openai_client = get_openai_client()
        query_vector = get_embedding(openai_client, semantic_query)
        body["knn"] = {
            "field": "embedding",
            "query_vector": query_vector,
            "k": max_results,
            "num_candidates": max(max_results * 3, 100),
            "filter": {"bool": {"filter": filters}},
        }

    return client.search(index=target_index, body=body)


def get_all_indices():
    """사용 가능한 모든 인덱스 목록 조회"""
    client = get_client()
    return list(client.indices.get_alias(index="*").keys())
