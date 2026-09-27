import io
import json
import zipfile

import psycopg
import shapefile

from noa_data.loaders.common import pending_files, record_loaded


SEOUL_SIDO = "11"


def load_admin_dong(conn: psycopg.Connection) -> int:
    """
    행정동 경계 GeoJSON (전국, 버전별) → admin_dong (서울만)

    새 버전 파일이 들어오면 서울 행정동 전체를 그 버전으로 바꾼다.
    """

    files = pending_files(conn, "admdong_boundary/*/HangJeongDong_*.geojson")
    total = 0

    for path in files:
        version = path.parent.name
        features = json.loads(path.read_text(encoding="utf-8"))["features"]
        seoul = [f for f in features if f["properties"].get("sido") == SEOUL_SIDO]

        with conn.transaction():
            conn.execute("DELETE FROM admin_dong")

            for feature in seoul:
                properties = feature["properties"]

                conn.execute(
                    """
                    INSERT INTO admin_dong (adm_code, adm_cd2, adm_nm, sgg_code, sgg_nm, boundary, version)
                    VALUES (%s, %s, %s, %s, %s,
                            ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))::geography, %s)
                    """,
                    (
                        properties["adm_cd2"][:8],
                        properties["adm_cd2"],
                        properties["adm_nm"],
                        properties["sgg"],
                        properties.get("sggnm"),
                        json.dumps(feature["geometry"]),
                        version,
                    ),
                )

            record_loaded(conn, path, "admdong_boundary", len(seoul))

        total += len(seoul)
        print(f"  admin_dong ← {version}: 서울 {len(seoul)}개")

    return total


def load_citydata_area_boundary(conn: psycopg.Connection) -> int:
    """
    121장소 영역 SHP (서울 열린데이터광장 OA-21285, WGS84) → citydata_area.boundary
    """

    files = pending_files(conn, "seoul_files/OA-21285/*121장소 영역*.zip")
    total = 0

    for path in files:
        with zipfile.ZipFile(path) as archive:
            base = next(name for name in archive.namelist() if name.endswith(".shp"))[:-4]
            reader = shapefile.Reader(
                shp=io.BytesIO(archive.read(base + ".shp")),
                shx=io.BytesIO(archive.read(base + ".shx")),
                dbf=io.BytesIO(archive.read(base + ".dbf")),
                encoding="utf-8",
            )

            with conn.transaction():
                count = 0

                for shape_record in reader.iterShapeRecords():
                    result = conn.execute(
                        """
                        UPDATE citydata_area
                        SET boundary = ST_Multi(ST_MakeValid(
                                ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))::geography
                        WHERE area_cd = %s
                        """,
                        (
                            json.dumps(shape_record.shape.__geo_interface__),
                            shape_record.record["AREA_CD"],
                        ),
                    )
                    count += result.rowcount

                record_loaded(conn, path, "citydata_area_boundary", count)

        total += count
        print(f"  citydata_area.boundary ← {path.name}: {count}개")

    return total
