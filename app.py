import streamlit as st
import pandas as pd
import datetime
from io import BytesIO
from elastic_api import search_stock_hybrid
from elk_utils import (
    INDEX_NAME,
    get_es_client,
    get_openai_client,
    answer_question,
    search_card_details,
)

st.set_page_config(page_title="Elasticsearch 주식 종목 조회", page_icon="🔍", layout="wide")

st.title("🔍 엘라스틱서치 주식 종목 조회")
st.markdown(
    """
    <style>
    [data-testid="stSidebar"][aria-expanded="true"] > div:first-child{width:280px;}
    .stDataFrame {width: 100%;}
    </style>
    """, unsafe_allow_html=True)

st.sidebar.header("📋 하이브리드 검색 조건")
st.sidebar.markdown("---")

semantic_query = st.sidebar.text_input('🧠 업종/주요제품(semantic)', value="")
lexical_query = st.sidebar.text_input('🔎 기타 컬럼(lexical)', value="")
market_option = st.sidebar.selectbox('🏷️ 시장구분', options=["전체", "코스피", "코스닥", "코넥스"])
max_results = st.sidebar.slider('📊 최대 결과 수', min_value=10, max_value=1000, value=100, step=10)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 날짜 범위 검색")
today = datetime.date.today()
date_range = st.sidebar.date_input(
    "회사 상장일",
    [datetime.date(1960, 1, 1), today])
clicked_hybrid = st.sidebar.button("🔍 하이브리드 검색", use_container_width=True)


def normalize_es_result(result):
    """Elasticsearch 응답 타입을 dict로 정규화."""
    if isinstance(result, dict):
        return result
    if hasattr(result, "body") and isinstance(result.body, dict):
        return result.body
    if hasattr(result, "to_dict"):
        return result.to_dict()
    raise TypeError(f"지원하지 않는 Elasticsearch 응답 타입: {type(result)}")


def display_results(result, title):
    """검색 결과를 표시하고 다운로드 옵션 제공"""
    result_dict = normalize_es_result(result)
    hits = result_dict.get("hits", {}).get("hits", [])
    total_info = result_dict.get("hits", {}).get("total", 0)
    total_hits = total_info.get("value", 0) if isinstance(total_info, dict) else total_info

    st.subheader(title)

    if not hits:
        st.warning("⚠️ 검색 결과가 없습니다. 검색 조건을 확인해주세요.")
        return

    st.success(f"✅ 총 {total_hits}건 중 {len(hits)}건 조회됨")

    # 결과 데이터를 DataFrame으로 변환
    source_data = [entry["_source"] for entry in hits]
    df = pd.DataFrame(source_data)

    # 탭으로 결과 표시
    tab1, tab2 = st.tabs(["📊 테이블 보기", "📝 원본 데이터"])

    with tab1:
        st.dataframe(df, use_container_width=True)

    with tab2:
        with st.expander("원본 JSON 데이터 보기"):
            st.json(hits)

    # 다운로드 버튼
    st.markdown("### 📥 데이터 다운로드")
    csv_data = df.to_csv(index=False, encoding='utf-8-sig')
    excel_data = BytesIO()
    df.to_excel(excel_data, index=False, engine='openpyxl')
    excel_data.seek(0)

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        st.download_button(
            "📄 CSV 다운로드",
            csv_data,
            file_name=f'{INDEX_NAME}_data.csv',
            mime='text/csv',
            use_container_width=True)
    with col2:
        st.download_button(
            "📗 Excel 다운로드",
            excel_data,
            file_name=f'{INDEX_NAME}_data.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True)


if "hybrid_result" not in st.session_state:
    st.session_state.hybrid_result = None
if "hybrid_error" not in st.session_state:
    st.session_state.hybrid_error = None
if "hybrid_notice" not in st.session_state:
    st.session_state.hybrid_notice = None
if "rag_answer" not in st.session_state:
    st.session_state.rag_answer = None
if "rag_docs" not in st.session_state:
    st.session_state.rag_docs = []
if "rag_mode" not in st.session_state:
    st.session_state.rag_mode = None
if "rag_details" not in st.session_state:
    st.session_state.rag_details = []
if "rag_error" not in st.session_state:
    st.session_state.rag_error = None

# 하이브리드 검색 실행 (사이드바 버튼)
if clicked_hybrid:
    if len(date_range) < 2:
        st.session_state.hybrid_error = "⚠️ 시작일과 종료일을 모두 선택해주세요."
    else:
        start_p = date_range[0]
        end_p = date_range[1] + datetime.timedelta(days=1)
        market = "" if market_option == "전체" else market_option
        with st.spinner("🔄 검색 중..."):
            try:
                st.session_state.hybrid_result = search_stock_hybrid(
                    index_name=INDEX_NAME,
                    semantic_query=semantic_query,
                    lexical_query=lexical_query,
                    market=market,
                    start_date=start_p,
                    end_date=end_p,
                    max_results=max_results,
                )
                st.session_state.hybrid_error = None
                st.session_state.hybrid_notice = None
            except Exception as e:
                # semantic 검색 실패 시 lexical-only로 1회 fallback
                if semantic_query.strip():
                    try:
                        st.session_state.hybrid_result = search_stock_hybrid(
                            index_name=INDEX_NAME,
                            semantic_query="",
                            lexical_query=lexical_query,
                            market=market,
                            start_date=start_p,
                            end_date=end_p,
                            max_results=max_results,
                        )
                        st.session_state.hybrid_error = None
                        st.session_state.hybrid_notice = (
                            f"⚠️ semantic 검색을 건너뛰고 lexical 검색 결과를 표시합니다. "
                            f"(원인: {e})"
                        )
                    except Exception as fallback_e:
                        st.session_state.hybrid_error = f"❌ 검색 중 오류가 발생했습니다: {fallback_e}"
                        st.session_state.hybrid_notice = None
                else:
                    st.session_state.hybrid_error = f"❌ 검색 중 오류가 발생했습니다: {e}"
                    st.session_state.hybrid_notice = None

main_tab1, main_tab2 = st.tabs(["🔎 하이브리드 검색", "💬 RAG 질의응답"])

with main_tab1:
    st.caption("semantic: 업종/주요제품(embedding), lexical: 회사명/시장구분/종목코드/대표자명/지역/상장일")
    if not semantic_query.strip() and not lexical_query.strip():
        st.info("검색어가 비어 있어 필터(시장구분/상장일) 기준으로 조회됩니다.")
    if st.session_state.hybrid_notice:
        st.warning(st.session_state.hybrid_notice)
    if st.session_state.hybrid_error:
        st.error(st.session_state.hybrid_error)
        st.info("💡 Elasticsearch 서버 연결 상태를 확인해주세요.")
    elif st.session_state.hybrid_result is not None:
        display_results(st.session_state.hybrid_result, "하이브리드 검색 결과")
    else:
        st.info("왼쪽 사이드바에서 조건을 입력한 뒤 `하이브리드 검색` 버튼을 눌러주세요.")

with main_tab2:
    with st.form("rag_question_form"):
        question = st.text_input(
            "질문을 입력하세요",
            placeholder="예: 2차전지 관련 주요 제품을 가진 코스닥 상장 종목 알려줘",
        )
        search_mode = st.radio(
            "검색 방식",
            ["자동", "lexical", "semantic"],
            horizontal=True,
        )
        clicked_rag = st.form_submit_button("💬 RAG 답변 생성")

    if clicked_rag:
        if not question.strip():
            st.session_state.rag_error = "⚠️ 질문을 입력해주세요."
        else:
            try:
                es = get_es_client()
                openai_client = get_openai_client()
                mode_map = {"자동": "auto", "lexical": "lexical", "semantic": "semantic"}
                selected_mode = mode_map[search_mode]

                with st.spinner("🤖 답변 생성 중..."):
                    answer, relevant_docs, actual_mode = answer_question(
                        es, openai_client, question, search_type=selected_mode
                    )
                    details = search_card_details(es, relevant_docs) if relevant_docs else []

                st.session_state.rag_answer = answer
                st.session_state.rag_docs = relevant_docs
                st.session_state.rag_mode = actual_mode
                st.session_state.rag_details = details
                st.session_state.rag_error = None
            except Exception as e:
                st.session_state.rag_error = f"❌ RAG 처리 중 오류가 발생했습니다: {e}"

    if st.session_state.rag_error:
        st.error(st.session_state.rag_error)
    elif st.session_state.rag_answer:
        st.info(f"검색 유형: {st.session_state.rag_mode}")
        st.markdown(st.session_state.rag_answer)
        if st.session_state.rag_docs:
            st.markdown("### 📌 관련 종목")
            st.write(", ".join(st.session_state.rag_docs))
        if st.session_state.rag_details:
            st.markdown("### 📊 종목 상세 정보")
            st.dataframe(pd.DataFrame(st.session_state.rag_details), use_container_width=True)
    else:
        st.info("질문을 입력하고 `RAG 답변 생성` 버튼을 눌러주세요.")
