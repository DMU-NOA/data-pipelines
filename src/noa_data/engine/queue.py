"""PostgreSQL-backed stage queue: recoverable after Docker restart."""
import logging
from datetime import datetime, timedelta, timezone

from noa_data.db.connection import connect
from noa_data.engine import citydata

LOG = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def enqueue(source: str, stage: str, batch_key: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO pipeline_jobs (source, stage, batch_key)
               VALUES (%s,%s,%s) ON CONFLICT (source,stage,batch_key) DO NOTHING""",
            (source, stage, batch_key),
        )


def recover_interrupted() -> None:
    with connect() as conn:
        count = conn.execute(
            """UPDATE pipeline_jobs SET state='pending', run_after=now(),
               last_error='recovered after pipeline restart'
               WHERE state='running' RETURNING id"""
        ).fetchall()
    LOG.info("복구된 작업: %d건", len(count))


def _claim() -> tuple | None:
    # The row lock prevents a second worker claiming the same job.
    with connect() as conn:
        with conn.transaction():
            row = conn.execute(
                """SELECT id, source, stage, batch_key, attempts
                   FROM pipeline_jobs
                   WHERE state='pending' AND run_after <= now()
                   ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"""
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE pipeline_jobs SET state='running', attempts=attempts+1,
                       started_at=now(), last_error=NULL WHERE id=%s""", (row[0],)
                )
    return row


def process_one() -> bool:
    row = _claim()
    if row is None:
        return False
    job_id, source, stage, batch_key, attempts = row
    try:
        if source != "citydata":
            raise ValueError(f"미지원 데이터 소스: {source}")
        if stage == "collect":
            # Each scheduled slot has one durable collection request.
            collected_file = citydata.collect()
            enqueue("citydata", "process", collected_file)
        elif stage == "process":
            citydata.process(batch_key)
            enqueue("citydata", "serve", batch_key)
        elif stage == "serve":
            outcome = citydata.serve()
            LOG.info("CityData service refreshed: actual=%s predicted=%s hourly=%s", *outcome)
        else:
            raise ValueError(f"미지원 단계: {stage}")
        with connect() as conn:
            conn.execute(
                """UPDATE pipeline_jobs SET state='succeeded', finished_at=now()
                   WHERE id=%s""", (job_id,)
            )
        LOG.info("작업 성공: #%s %s/%s %s", job_id, source, stage, batch_key)
    except Exception as exc:
        count = attempts + 1
        state = "failed" if count >= MAX_ATTEMPTS else "pending"
        # Exponential backoff capped at 1 hour; no busy-loop on API failure.
        retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=min(3600, 60 * (2 ** max(0, count - 1)))
        )
        with connect() as conn:
            conn.execute(
                """UPDATE pipeline_jobs
                   SET state=%s, run_after=%s, last_error=%s, finished_at=now()
                   WHERE id=%s""",
                (state, retry_at, f"{type(exc).__name__}: {exc}"[:1500], job_id),
            )
        LOG.exception("작업 실패: #%s %s/%s (%s회)", job_id, source, stage, count)
    return True
