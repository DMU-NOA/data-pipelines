from pathlib import Path

from noa_data.collectors.common import get_env, now_kst, save_raw
from noa_data.collectors.seoul_open_api import fetch_all_rows


# 스마트서울 도시데이터 센서(S-DoT) 유동인구 측정 정보
#
# 두 API는 보관 범위와 지연이 다르고 필드 이름도 조금 다르다.
# 둘 다 지난 데이터가 매일 사라지므로 계속 수집해서 쌓아야 한다.
#
# - recent   (IotVdata018, OA-15964): 등록일(REG_DTTM) 기준 최근 약 한 달, 약 4일 지연
#            필드: MODEL_NM, SERIAL_NO, SENSING_TIME, REGION, AUTONOMOUS_DISTRICT,
#                  ADMINISTRATIVE_DISTRICT, VISITOR_COUNT, REG_DTTM
# - realtime (sDoTPeople, OA-22832): 측정일(SENSING_TIME) 기준 최근 약 16일, 10~20분 지연
#            필드: MODELNAME, SERIAL, SENSING_TIME, REGION, AUTONOMOUS_DISTRICT,
#                  ADMINISTRATIVE_DISTRICT, VISITOR_COUNT, DATE, DATA_NO
#
# CSV 파일과 달리 API는 필드 이름이 붙어 오므로 컬럼이 어긋나는 문제가 없다.
APIS = {
    "recent": {
        "service": "IotVdata018",
        "source": "sdot_recent",
        # 첫 번째 선택 인자는 자치구다. 전체를 받기 위해 공백으로 둔다.
        "args": lambda date: (" ", date),
    },
    "realtime": {
        "service": "sDoTPeople",
        "source": "sdot_realtime",
        "args": lambda date: (date,),
    },
}


def collect(api: str, date: str) -> Path | None:
    """
    하루치 S-DoT 측정값을 원본 그대로 저장한다.

    date: YYYY-MM-DD
    - recent 는 등록일, realtime 은 측정일 기준이다.
    - 같은 날짜를 여러 번 수집하면 파일이 여러 개 생긴다.
      중복은 DB 적재 때 (센서, 측정시각) 으로 거른다.
    """

    get_env("SEOUL_API_KEY")

    config = APIS[api]
    collected_at = now_kst()

    rows, total = fetch_all_rows(config["service"], *config["args"](date))

    if not rows:
        print(f"{api:8} {date}: 데이터 없음")
        return None

    path = save_raw(
        config["source"],
        f"{config['service']}_{date}",
        {
            "service": config["service"],
            "date": date,
            "list_total_count": total,
            "rows": rows,
        },
        collected_at,
    )

    print(f"{api:8} {date}: {len(rows):,} / {total:,} → {path}")

    return path
