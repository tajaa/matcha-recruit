"""Media stays on a dedicated queue/host. Default worker does light recovery/mail."""
import asyncio
import logging
from uuid import UUID

from app.workers.celery_app import celery_app, consumes_queue

logger = logging.getLogger(__name__)


@celery_app.task(name="recaps.reconcile")
def reconcile_recaps():
    from app.matcha.services.matcha_work.recaps.reconcile import sweep
    try:
        reschedule = asyncio.run(sweep())
    except Exception:
        logger.warning("recap sweep failed", exc_info=True)
        reschedule = True
    if reschedule:
        reconcile_recaps.apply_async(countdown=60, queue="celery")


def require_media_queue():
    from app.matcha.services.matcha_work.recaps.settings import RENDER_QUEUE
    if not consumes_queue(RENDER_QUEUE):
        raise RuntimeError("recap media requires its dedicated queue")


@celery_app.task(name="recaps.render", soft_time_limit=240, time_limit=300)
def render_recap(recap_id: str):
    require_media_queue()
    from app.matcha.services.matcha_work.recaps.reconcile import render_job
    asyncio.run(asyncio.wait_for(render_job(UUID(recap_id)), timeout=240))


@celery_app.task(name="recaps.deliver", soft_time_limit=55, time_limit=60)
def deliver_recap(delivery_id: str):
    from app.matcha.services.matcha_work.recaps.delivery import deliver
    asyncio.run(deliver(UUID(delivery_id)))


@celery_app.task(name="recaps.cleanup", soft_time_limit=90, time_limit=120)
def cleanup_recap(cleanup_id: str):
    require_media_queue()
    from app.matcha.services.matcha_work.recaps.reconcile import cleanup_job
    asyncio.run(asyncio.wait_for(cleanup_job(UUID(cleanup_id)), timeout=90))
