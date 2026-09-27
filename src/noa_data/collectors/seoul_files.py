import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from noa_data.collectors.common import RAW_DATA_DIR


SOURCE = "seoul_files"

DATASET_URL = "https://data.seoul.go.kr/dataList/{inf_id}/F/1/datasetView.do"
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"

# 서울 열린데이터광장 파일 데이터셋
# match: 받을 파일 이름 패턴
DATASETS = {
    "sdot_sensor": {
        "inf_id": "OA-15964",
        "name": "S-DoT 센서 설치 위치정보",
        "match": r"위치정보.*\.xlsx$",
    },
    "sdot_history": {
        "inf_id": "OA-15964",
        "name": "S-DoT 유동인구 과거 파일 (주간 CSV, 연간 ZIP)",
        "match": r"^S-DoT_WALK_.*\.(csv|zip)$",
    },
    "citydata_area": {
        "inf_id": "OA-21285",
        "name": "서울시 주요 121장소 목록과 영역",
        "match": r"121장소.*\.(zip|xlsx)$",
    },
    "foreigner_block": {
        "inf_id": "OA-14980",
        "name": "집계구 단위 서울 생활인구(단기체류 외국인) 월별 파일",
        "match": r"^TEMP_FOREIGNER_\d{6}\.zip$",
    },
    "foreigner_dong": {
        "inf_id": "OA-14993",
        "name": "행정동 단위 서울 생활인구(단기체류 외국인) 월별 파일",
        "match": r"^TEMP_FOREIGNER_DONG_\d{6}\.zip$",
    },
    "living_population": {
        "inf_id": "OA-14991",
        "name": "행정동 단위 서울 생활인구(내국인) 월별 파일",
        "match": r"^LOCAL_PEOPLE_DONG_\d{6}\.zip$",
    },
}

ROW_PATTERN = re.compile(
    r"<span title=\"(?P<name>[^\"]+)\" onclick=\"javascript:downloadFile\('(?P<seq>\d+)'\);\">"
    r".*?</td>\s*<td>(?P<size>[\d.,]+)</td>\s*<td>(?P<modified>[\d.]+)</td>",
    re.DOTALL,
)


@dataclass
class RemoteFile:
    name: str
    seq: str
    size_mb: float
    modified: str

    @property
    def data_date(self) -> date | None:
        """
        파일 이름에 들어 있는 첫 날짜 (데이터 기간의 시작).

        예:
        S-DoT_WALK_2026.09.07-09.13.csv                  -> 2026-09-07
        S-DoT_WALK_2022년(2022.01.03~2023.01.01).zip     -> 2022-01-03
        LOCAL_PEOPLE_DONG_202607.zip                      -> 2026-07-01
        """

        match = re.search(r"(20\d{2})\.?(\d{2})(?:\.(\d{2}))?(?!\d)", self.name)

        if not match:
            return None

        year, month, day = match.groups()

        return date(int(year), int(month), int(day or 1))


def list_files(inf_id: str) -> tuple[str, list[RemoteFile]]:
    """
    데이터셋 파일 탭에서 파일 목록과 infSeq 를 읽는다.
    """

    page = requests.get(DATASET_URL.format(inf_id=inf_id), timeout=30)
    page.raise_for_status()

    # 페이지에 infSeq 가 여러 개 있으므로 파일 다운로드 폼(frmFile) 안의 값을 쓴다.
    inf_seq = re.search(
        r'<form name="frmFile".*?name="infSeq" value="(\d+)"',
        page.text,
        re.DOTALL,
    )

    if not inf_seq:
        raise RuntimeError(f"{inf_id} 페이지에서 infSeq 를 찾지 못했습니다. 페이지 구조가 바뀌었을 수 있습니다.")

    files = [
        RemoteFile(
            name=match["name"],
            seq=match["seq"],
            size_mb=float(match["size"].replace(",", "")),  # 예: 1,172.74
            modified=match["modified"].rstrip("."),
        )
        for match in ROW_PATTERN.finditer(page.text)
    ]

    return inf_seq.group(1), files


def download(inf_id: str, inf_seq: str, file: RemoteFile, directory: Path) -> Path:
    """
    파일 하나를 내려받는다. 받는 도중 실패하면 부분 파일을 남기지 않는다.
    """

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / file.name
    partial = path.with_name(path.name + ".part")

    with requests.post(
        DOWNLOAD_URL,
        data={"infId": inf_id, "seqNo": "", "seq": file.seq, "infSeq": inf_seq},
        stream=True,
        timeout=120,
    ) as response:
        response.raise_for_status()

        if "attachment" not in response.headers.get("Content-Disposition", ""):
            raise RuntimeError(f"파일이 아닌 응답: {file.name} {response.text[:200]}")

        with open(partial, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                output.write(chunk)

    partial.replace(path)

    return path


def collect(
    dataset: str,
    since: date | None = None,
    dry_run: bool = False,
) -> list[Path]:
    """
    데이터셋에서 패턴에 맞는 파일을 원본 그대로 내려받는다.

    저장: data/raw/seoul_files/<inf_id>/<원본 파일 이름>
    이미 받은 파일은 건너뛴다. 파일 이름에 기간이나 버전이 들어 있어서
    새 파일은 이름이 달라진다.

    since: 파일 이름의 날짜가 이 날짜 이후인 파일만 받는다.
    dry_run: 받지 않고 목록과 용량만 출력한다.
    """

    config = DATASETS[dataset]
    inf_id = config["inf_id"]
    directory = RAW_DATA_DIR / SOURCE / inf_id

    inf_seq, files = list_files(inf_id)

    targets = [
        file
        for file in files
        if re.search(config["match"], file.name)
        and (since is None or (file.data_date and file.data_date >= since))
    ]
    todo = [file for file in targets if not (directory / file.name).exists()]

    print(
        f"{config['name']} ({inf_id}): 대상 {len(targets)}개 / "
        f"새로 받을 파일 {len(todo)}개, {sum(file.size_mb for file in todo):,.1f}MB"
    )

    if dry_run:
        for file in todo:
            print(f"  {file.name}  {file.size_mb}MB  (수정일 {file.modified})")
        return []

    paths: list[Path] = []

    for index, file in enumerate(todo, start=1):
        path = download(inf_id, inf_seq, file, directory)
        paths.append(path)
        print(f"  [{index}/{len(todo)}] {file.name} ({file.size_mb}MB)")

    return paths
