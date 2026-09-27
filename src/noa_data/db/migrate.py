from noa_data.collectors.common import PROJECT_ROOT
from noa_data.db.connection import connect


MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def main() -> None:
    """
    migrations/*.sql 을 파일 이름 순서대로, 아직 적용하지 않은 것만 적용한다.

    파일 하나는 트랜잭션 하나로 적용되므로, 중간에 실패하면 그 파일 전체가 취소된다.
    이미 적용한 파일은 수정하지 말고 새 번호의 파일을 추가한다.
    """

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version     text PRIMARY KEY,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.commit()

        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM public.schema_migrations")
        }

        pending = [
            path
            for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
            if path.stem not in applied
        ]

        if not pending:
            print("적용할 마이그레이션이 없습니다.")
            return

        for path in pending:
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO public.schema_migrations (version) VALUES (%s)",
                    (path.stem,),
                )

            print(f"적용: {path.name}")


if __name__ == "__main__":
    main()
