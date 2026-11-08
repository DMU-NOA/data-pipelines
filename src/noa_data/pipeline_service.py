"""Long-running single-process Docker entrypoint; no Windows scheduler needed."""
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from noa_data.db.migrate import main as migrate
from noa_data.engine.queue import enqueue, process_one, recover_interrupted

LOG = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
HEARTBEAT = Path("/tmp/noa_pipeline_heartbeat")


def _slot_key() -> str:
    now = datetime.now(KST)
    minute = (now.minute // 15) * 15
    return now.replace(minute=minute, second=0, microsecond=0).isoformat()


def schedule_citydata() -> None:
    enqueue("citydata", "collect", _slot_key())


def drain_queue() -> None:
    # Run at most one stage per tick so long collection tasks do not queue
    # concurrent copies of themselves. APScheduler max_instances=1.
    try:
        process_one()
    finally:
        HEARTBEAT.touch()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("PIPELINE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    LOG.info("NOA Pipeline Docker service starting")
    # Wait for an externally-managed database at startup.
    while True:
        try:
            migrate()
            recover_interrupted()
            break
        except Exception:
            LOG.exception("DB 초기화 실패. 30초 후 재시도")
            time.sleep(30)

    scheduler = BackgroundScheduler(
        timezone=KST,
        job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 300},
    )
    scheduler.add_job(
        schedule_citydata, CronTrigger(minute="0,15,30,45", timezone=KST),
        id="citydata_collection", replace_existing=True,
    )
    scheduler.add_job(
        drain_queue, "interval", seconds=10, id="stage_runner",
        replace_existing=True, max_instances=1,
    )
    scheduler.start()
    if os.getenv("PIPELINE_COLLECT_ON_START", "true").lower() in ("true", "1", "yes"):
        schedule_citydata()
    HEARTBEAT.touch()
    LOG.info("CityData 15분 수집 및 단계별 가공/적재 스케줄 등록 완료")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        LOG.info("Pipeline stopping")
    finally:
        scheduler.shutdown(wait=True)


if __name__ == "__main__":
    main()
