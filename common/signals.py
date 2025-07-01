import logging
import json
from django.utils import timezone
from common.models import TaskHistory
from huey.contrib.djhuey import HUEY
from huey.signals import (
    SIGNAL_COMPLETE,
    SIGNAL_ERROR,
    SIGNAL_ENQUEUED,
)

logger = logging.getLogger(__name__)


def _serialize(data):
    try:
        return json.dumps(data, indent=2, default=str)
    except Exception as e:
        return f"<serialization error: {e}>"





@HUEY.signal(SIGNAL_ENQUEUED)
def on_task_started(signal, task, *args, **kwargs):
    TaskHistory.objects.create(
        name=getattr(task, "name", str(task)),
        task_id=getattr(task, "id", None),
        status="started",
        started_at=timezone.now(),
        args=_serialize(getattr(task, "args", [])),
        kwargs=_serialize(getattr(task, "kwargs", {})),
    )


@HUEY.signal(SIGNAL_COMPLETE)
def on_task_finished(signal, task, *args, **kwargs):
    updated = (
        TaskHistory.objects.filter(
            task_id=getattr(task, "id", None),
            status="started",
            finished_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )
    if updated:
        updated.status = "finished"
        updated.finished_at = timezone.now()
        if updated.started_at:
            updated.duration = (updated.finished_at - updated.started_at).total_seconds()
        updated.save()
    else:
        logger.warning(f"Task finished but no started record found: {task}")


@HUEY.signal(SIGNAL_ERROR)
def on_task_error(signal, task, exc, *args, **kwargs):
    updated = (
        TaskHistory.objects.filter(
            task_id=getattr(task, "id", None),
            status="started",
            finished_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )
    if updated:
        updated.status = "error"
        updated.finished_at = timezone.now()
        if updated.started_at:
            updated.duration = (updated.finished_at - updated.started_at).total_seconds()
        updated.error = str(exc)
        updated.save()
    else:
        logger.error(f"Task error but no started record found: {task} - {exc}")
