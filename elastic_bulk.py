from elasticsearch import Elasticsearch
from elasticsearch import helpers
import pandas as pd
import json
from tqdm import tqdm
from elk_utils import (
    get_es_client,
    get_openai_client,
    get_embedding,
    get_index_mapping,
    INDEX_NAME,
)

tqdm.pandas()

def get_stock_info():
    base_url =  "http://kind.krx.co.kr/corpgeneral/corpList.do"    
    method = "download"
    url = "{0}?method={1}".format(base_url, method)   
    df = pd.read_html(url, header=0, encoding='euc-kr')[0]
    df['종목코드']= df['종목코드'].apply(lambda x: f"{x:06}")     
    return df

df = get_stock_info()
es = get_es_client()
openai_client = get_openai_client()

# 각 행의 category 컬럼에 임베딩 적용
print(f"총 {len(df)}건 임베딩 생성 시작...")

cols = ["업종", "주요제품"]  # JSON으로 묶을 컬럼들

# 1) 문자열 JSON으로 저장하고 싶으면
df["embedding"] = df[cols].progress_apply(
    lambda r: get_embedding(openai_client, json.dumps(r.to_dict(), ensure_ascii=False)),
    axis=1,
)

print("임베딩 생성 완료")

# 결과를 새로운 CSV 파일로 저장
df.to_csv("df_stock_info.csv", index=False)

# JSON 변환
json_records = json.loads(df.to_json(orient="records"))

# 인덱스 삭제 후 매핑과 함께 재생성
es.options(ignore_status=[400, 404]).indices.delete(index=INDEX_NAME)
es.indices.create(index=INDEX_NAME, mappings=get_index_mapping())

# 벌크 색인
actions = [
    {"_op_type": "index", "_index": INDEX_NAME, "_source": row}
    for row in json_records
]
helpers.bulk(es, actions)
print(f"{len(actions)}건 색인 완료")
