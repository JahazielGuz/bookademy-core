import os

from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("bookademy")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def record_what_this_worker_loaded(**kwargs) -> None:
    """Fingerprint the code this worker is actually running.

    A worker never re-reads its files, so without a record of what it loaded there is
    no way to tell a worker that needs restarting from one that does not — and both
    guesses are expensive. `manage.py worker_status` answers it from this.
    """
    from documents.staleness import record_boot

    record_boot()
