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


def update_last_task_result(task_name, result):
    """
    Finds the most recent TaskHistory entry for a given task name with a null result,
    runs the task function, and stores the result in the TaskHistory.

    Args:
        task_name (str): Name of the task to find in TaskHistory.
        task_function (callable): The task function to execute and store result for.

    Returns:
        dict or any: The actual result returned by the task function.
    """
    task = (
        TaskHistory.objects
        .filter(name=task_name, result__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if not task:
        logger.warning(f"No TaskHistory entry with result=None found for task '{task_name}'")
        return None

    try:
        task.result = _serialize(result)
        task.updated_at = timezone.now()
        task.save()
        print(f"✅ Updated result for task {task.task_id}")
        return result
    except Exception as e:
        print(f"❌ Failed to run or update task: {e}")
        return None


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
        updated.result = _serialize(getattr(task, "value", ""))
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
