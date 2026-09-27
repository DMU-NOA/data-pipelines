from noa_data.collectors.common import get_env, get_json


BASE_URL = "http://openapi.seoul.go.kr:8088"

# 서울 열린데이터광장은 한 번에 최대 1,000건까지 조회할 수 있다.
PAGE_SIZE = 1000

NO_DATA_CODE = "INFO-200"


def fetch_page(
    service: str,
    start: int,
    end: int,
    *args: str,
) -> dict:
    """
    서울 열린데이터광장 API 한 페이지를 조회한다.

    URL 형식:
    /{KEY}/json/{SERVICE}/{START}/{END}/{ARG1}/{ARG2}...
    """

    key = get_env("SEOUL_API_KEY")

    path = "/".join(
        [BASE_URL, key, "json", service, str(start), str(end), *args]
    )

    return get_json(path)


def fetch_all_rows(service: str, *args: str) -> tuple[list[dict], int]:
    """
    목록형 서비스의 모든 페이지를 조회해서 row를 합친다.

    반환값: (rows, list_total_count)
    데이터가 없으면 ([], 0)을 반환한다.
    """

    # sample 키는 1~5번째 row만 조회할 수 있으므로 첫 페이지만 받는다.
    is_sample = get_env("SEOUL_API_KEY") == "sample"
    page_size = 5 if is_sample else PAGE_SIZE

    rows: list[dict] = []
    total = None
    start = 1

    while total is None or start <= total:
        end = start + page_size - 1
        payload = fetch_page(service, start, end, *args)

        body = payload.get(service)

        if body is None:
            result = payload.get("RESULT", {})
            code = result.get("CODE")

            if code == NO_DATA_CODE:
                return [], 0

            raise RuntimeError(
                f"{service} 응답 오류: {code} {result.get('MESSAGE')}"
            )

        total = int(body["list_total_count"])
        page_rows = body.get("row", [])
        rows.extend(page_rows)

        if not page_rows or is_sample:
            break

        start = end + 1

    return rows, total
