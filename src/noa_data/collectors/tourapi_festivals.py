from pathlib import Path

from noa_data.collectors.common import get_env, now_kst, save_raw
from noa_data.collectors.tourapi_places import (
    LANGUAGE_SERVICES,
    SEOUL_LDONG_REGN_CD,
    extract_items,
    fetch_all_pages,
)


SOURCE = "tourapi_festivals"


def collect(
    event_start_date: str,
    languages: list[str] | None = None,
) -> list[Path]:
    """
    event_start_date(YYYYMMDD) 이후에 열리는 서울 축제/공연/행사를
    언어별로 나눠 원본 그대로 저장한다.

    목록(areaBasedList2)에는 없는 행사 기간(eventstartdate, eventenddate)과
    좌표가 함께 온다.
    """

    get_env("DATA_GO_KR_API_KEY")

    languages = languages or list(LANGUAGE_SERVICES)
    paths: list[Path] = []
    errors: dict[str, str] = {}

    for lang in languages:
        collected_at = now_kst()

        try:
            pages = fetch_all_pages(
                lang,
                "searchFestival2",
                {
                    "lDongRegnCd": SEOUL_LDONG_REGN_CD,
                    "eventStartDate": event_start_date,
                    "arrange": "C",
                },
            )

        except RuntimeError as error:
            errors[lang] = str(error).splitlines()[0]
            print(f"{lang:5} 실패: {errors[lang]}")
            continue

        count = sum(len(extract_items(page)) for page in pages)

        path = save_raw(
            SOURCE,
            f"festivals_{lang}_from_{event_start_date}",
            {
                "lang": lang,
                "event_start_date": event_start_date,
                "pages": pages,
            },
            collected_at,
        )
        paths.append(path)

        print(f"{lang:5} {count:>5,} → {path}")

    if not paths:
        raise RuntimeError(f"모든 언어가 실패했습니다: {errors}")

    return paths
