"""TourAPI 관광지 관련 데이터만 백업 후 초기화한다.

실측 CityData 이력, S-DoT, 교통, 날씨, 회원(accounts)은 보존한다.
실행: python -m noa_data.jobs.reset_tourism --confirm-reset
관광지 원본을 처음부터 다시 호출하려면 --fresh-collect 사용.
"""
import argparse
import shutil
from datetime import datetime
from pathlib import Path

from noa_data.collectors.common import PROJECT_ROOT, RAW_DATA_DIR
from noa_data.db.connection import connect


TOUR_SOURCES = ("tourapi_places", "tourapi_details", "tourapi_festivals")
TOUR_TABLES = (
    "place_nearby",
    "kto_place_match",
    "spot_mapping",
    "latest_congestion",
    "tour_spots",
    "tour_place_detail",
    "tour_festival",
    "tour_place",
)


def reset(conn, *, allow_delete_likes=False):
    """명시적 파괴 옵션이 있을 때만 관광지 관련 행을 삭제한다."""
    likes = conn.execute(
        "SELECT count(*) FROM likes WHERE content_id IS NOT NULL"
    ).fetchone()[0]
    if likes and not allow_delete_likes:
        raise RuntimeError(
            f"관광지 좋아요 {likes:,}건이 있습니다. 삭제하지 않았습니다. "
            "해당 사용자 데이터까지 지우려면 --allow-delete-likes를 지정하세요."
        )

    counts = {}
    with conn.transaction():
        if likes:
            conn.execute("DELETE FROM likes WHERE content_id IS NOT NULL")
            counts["likes"] = likes

        for table in TOUR_TABLES:
            result = conn.execute(f"DELETE FROM {table}")
            counts[table] = result.rowcount

        result = conn.execute(
            """DELETE FROM pipeline_load_history
               WHERE source = ANY(%s)
                  OR file_path LIKE 'tourapi_places/%'
                  OR file_path LIKE 'tourapi_details/%'
                  OR file_path LIKE 'tourapi_festivals/%'""",
            (list(TOUR_SOURCES),),
        )
        counts["tour_pipeline_load_history"] = result.rowcount

    return counts


def archive_raw_files():
    """기존 TourAPI 원본 파일을 지우지 않고 저장소 외부 백업 위치로 옮긴다."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = PROJECT_ROOT.parent / "noa-tourapi-raw-backup" / stamp
    moved = []
    for source in TOUR_SOURCES:
        src = RAW_DATA_DIR / source
        if src.exists():
            backup.mkdir(parents=True, exist_ok=True)
            dst = backup / source
            shutil.move(str(src), str(dst))
            moved.append(str(dst))
    return moved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-reset", action="store_true",
                        help="관광지 DB 데이터 삭제를 명시적으로 승인")
    parser.add_argument("--allow-delete-likes", action="store_true",
                        help="관광지 좋아요까지 삭제하는 데 동의")
    parser.add_argument("--fresh-collect", action="store_true",
                        help="기존 TourAPI 원본 파일을 외부 폴더에 보관 후 새로 수집")
    args = parser.parse_args()

    if not args.confirm_reset:
        with connect() as conn:
            likes = conn.execute(
                "SELECT count(*) FROM likes WHERE content_id IS NOT NULL"
            ).fetchone()[0]
            print(f"사전 확인: 관광지 관련 좋아요 {likes:,}건")
            for table in TOUR_TABLES:
                count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                print(f"{table}: {count:,}건 (삭제 후보)")
        print("실제 삭제는 수행하지 않았습니다. --confirm-reset 필요")
        return

    with connect() as conn:
        counts = reset(conn, allow_delete_likes=args.allow_delete_likes)
    print("관광지 관련 DB 초기화 완료:", counts)

    if args.fresh_collect:
        print("기존 TourAPI 원본 보관:", archive_raw_files())
        print("이제 collect_tourapi_places --lang ko 부터 새로 수집하세요.")


if __name__ == "__main__":
    main()
