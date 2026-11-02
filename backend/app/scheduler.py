"""Background jobs: a tick every 5 minutes and a nightly retrain."""
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from . import config
from .pipeline import Pipeline


def start(pipeline: Pipeline) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(pipeline.tick, "cron", minute=f"*/{config.STEP_MINUTES}", second=30,
                      max_instances=1, coalesce=True, id="tick")
    scheduler.add_job(pipeline.retrain, "cron", hour=config.RETRAIN_HOUR, minute=7, timezone=config.DISPLAY_TIMEZONE,
                      max_instances=1, coalesce=True, id="retrain")
    scheduler.start()

    def first_run():
        pipeline.tick()
        if pipeline.models is None:
            pipeline.retrain()

    threading.Thread(target=first_run, daemon=True, name="first-run").start()
    return scheduler
