import psycopg

from noa_data.collectors.common import get_env


def connect() -> psycopg.Connection:
    """
    data-pipeline/.env 의 DB_* 값으로 PostgreSQL 에 접속한다.

    autocommit 으로 연결하므로, 여러 문장을 묶으려면 with conn.transaction(): 을 쓴다.
    (autocommit 이 아니면 연결 전체가 하나의 트랜잭션이 되어,
    중간에 실패했을 때 앞에서 끝난 적재까지 모두 취소된다)
    """

    return psycopg.connect(
        host=get_env("DB_HOST"),
        port=get_env("DB_PORT"),
        dbname=get_env("DB_NAME"),
        user=get_env("DB_USER"),
        password=get_env("DB_PASSWORD"),
        autocommit=True,
    )
