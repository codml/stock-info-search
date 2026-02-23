# 🔍 엘라스틱서치 주식 종목 조회 (Elasticsearch Stock Search & RAG)

한국거래소(KRX)의 상장법인 데이터를 바탕으로 주식 종목을 검색하고, RAG(Retrieval-Augmented Generation) 기반 질의응답을 제공하는 Streamlit 웹 애플리케이션입니다. 

사용자는 업종과 주요제품의 의미론적(Semantic) 검색과 회사명, 종목코드 등의 어휘적(Lexical) 검색을 결합한 하이브리드 검색을 통해 원하는 주식 종목을 빠르고 정확하게 찾을 수 있습니다.

## ✨ 주요 기능

* **KRX 데이터 자동 수집 및 임베딩 생성**: 한국거래소에서 주식 종목 데이터를 수집한 후, OpenAI(`text-embedding-3-small`)를 활용해 업종 및 주요 제품에 대한 벡터 임베딩을 생성하여 Elasticsearch에 적재합니다.
* **하이브리드 검색 (Hybrid Search)**: 
  * **Semantic 검색**: 업종 및 주요제품 정보를 기반으로 유사도 검색을 수행합니다.
  * **Lexical 검색**: 회사명, 종목코드, 대표자명, 지역 등을 키워드 기반으로 검색합니다.
* **맞춤형 필터링**: 시장 구분(코스피, 코스닥, 코넥스, 전체) 및 상장일 기준 날짜 범위 필터링 기능을 지원합니다.
* **RAG 기반 챗봇 질의응답**: 사용자가 주식 관련 질문을 입력하면, 검색된 종목 정보와 OpenAI 모델(`gpt-4o-mini`)을 활용하여 근거 있는 답변을 제공합니다.
* **데이터 내보내기**: 조회된 검색 결과를 CSV 또는 Excel 파일 형식으로 편리하게 다운로드할 수 있습니다.

## 🛠 기술 스택

* **언어 및 프론트엔드**: Python, Streamlit, Pandas
* **검색 엔진**: Elasticsearch, Elasticsearch DSL
* **AI 및 임베딩**: OpenAI API (`text-embedding-3-small`, `gpt-4o-mini`)

## 🚀 설치 및 실행 방법

### 1. 사전 요구 사항
* 로컬 환경에 Elasticsearch 서버가 구동되어 있어야 합니다 (`http://localhost:9200`).
* OpenAI API 키가 필요합니다.

### 2. 의존성 패키지 설치
```bash
pip install -r requirements.txt
