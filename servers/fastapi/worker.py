import os
import json
import time
from pathlib import Path
from celery import Celery
from celery.signals import task_failure, worker_ready

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.generate_task",
        "tasks.source_import_task",
    ]
)

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/app/storage"))
# Fallback only for legacy failure handlers when args omit user_id.
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "")

# Generation is the long pole; the soft limit fires first so a task can write a
# failure status before the hard limit kills the worker process.
GENERATION_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "3600"))
GENERATION_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "3300"))

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Celery 6+: startup retries are no longer implied by broker_connection_retry.
    broker_connection_retry_on_startup=True,
    # Without limits a hung task held its slot indefinitely.
    task_time_limit=GENERATION_TIME_LIMIT,
    task_soft_time_limit=GENERATION_SOFT_TIME_LIMIT,
    # Late-acked generation must remain invisible longer than its hard limit.
    # Otherwise Redis redelivers the same task while the first worker still owns
    # it, and both processes overwrite one project's SVG/PPTX artifacts.
    broker_transport_options={
        "visibility_timeout": GENERATION_TIME_LIMIT + 900,
    },
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "2")),
    # One task per worker at a time: these are long, CPU- and memory-heavy jobs,
    # and prefetching them starves whichever queue happens to be idle.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_queue="generation",
    # PDF imports are bursty and used to queue behind interactive generation.
    task_routes={
        "tasks.generate_task.run_generation": {"queue": "generation"},
        "tasks.generate_task.compile_generation": {"queue": "generation"},
        "tasks.generate_task.fix_authored_slides": {"queue": "generation"},
        "tasks.source_import_task.parse_uploaded_source": {"queue": "source_import"},
    },
)


@worker_ready.connect
def reconcile_schema(**_kwargs):
    """Add any columns this worker's models expect but the database lacks.

    The API normally does this first, but a worker that reads settings before
    the API has started would otherwise fail on an unknown column. Done after
    startup, not at import, so an unreachable database does not stop the worker
    from booting and reporting the problem.
    """
    try:
        import models  # noqa: F401  (registers tables on the shared metadata)
        from database import ensure_schema

        ensure_schema()
    except Exception as error:
        print(f"[schema] worker could not reconcile the database schema: {error}")


@task_failure.connect
def mark_generation_failure(
    task_id=None,
    exception=None,
    args=None,
    sender=None,
    **kwargs,
):
    """Persist terminal generation failures for refresh-safe UI state."""
    task_name = getattr(sender, "name", "")
    if task_name not in {
        "tasks.generate_task.run_generation",
        "tasks.generate_task.compile_generation",
        "tasks.generate_task.fix_authored_slides",
        "tasks.source_import_task.parse_uploaded_source",
    } or not args:
        return
    try:
        is_source = task_name == "tasks.source_import_task.parse_uploaded_source"
        project_id = str(args[0] if is_source else args[1])
        user_id = DEFAULT_USER_ID
        if is_source and len(args) > 2:
            user_id = str(args[2])
        root = STORAGE_ROOT / user_id / project_id
        if is_source:
            from tasks.source_import import write_source_status

            write_source_status(
                root,
                "source_error",
                0,
                "PDF source parsing failed",
                message_key="source_status_error",
                task_id=task_id,
                error=str(exception or "source import task failed"),
            )
            return
        status_path = root / "status.json"
        payload = {
            "status": "failed",
            "progress": 0,
            "updated_at": int(time.time()),
            # The exception text is the diagnostic; the key gives the UI a
            # sentence it can translate to head it.
            "message": str(exception or "generation task failed"),
            "message_key": "status_generation_failed",
            "task_id": task_id,
        }
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        run_manifest_path = root / "validation" / "run_manifest.json"
        if run_manifest_path.is_file():
            run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
            run_manifest.update({"status": "failed", "error": str(exception or "generation task failed")})
            run_manifest_path.write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Unable to persist Celery generation failure: {exc}")
