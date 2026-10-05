"""Knowing when the worker needs restarting, and when it does not.

Both mistakes have cost something here: a worker left on stale code called an
endpoint that no longer existed, and restarting one for no reason risks interrupting
a run that is spending money.
"""

import pytest

from documents.staleness import KEY, _client, check, record_boot, task_dependency_files


@pytest.fixture(autouse=True)
def restore_fingerprint():
    """Put back whatever was there.

    Tests and a running worker share one Redis, so deleting the key would leave a
    live worker looking like it had never booted — the suite would be reporting a
    problem it caused itself.
    """
    client = _client()
    before = client.get(KEY)
    yield
    if before is None:
        client.delete(KEY)
    else:
        client.set(KEY, before)


def test_web_only_modules_are_not_task_dependencies():
    """A worker imports every view and serializer in the project, because
    django.setup() loads the URL conf. None of them affect a task, so editing one
    must not report the worker as stale."""
    files = task_dependency_files()

    assert not any("serializers.py" in f for f in files)
    assert not any("views.py" in f for f in files)
    assert not any("urls.py" in f for f in files)
    assert not any("admin.py" in f for f in files)


def test_the_modules_tasks_actually_use_are_dependencies():
    files = task_dependency_files()

    for expected in [
        "documents/tasks.py",
        "documents/events.py",
        "documents/locks.py",
        "curriculum/builders.py",
        "curriculum/models.py",
        "aiservice/client.py",
    ]:
        assert expected in files, f"{expected} should be watched"


def test_settings_count_even_though_tasks_never_import_them():
    """They reach the worker through django.conf, but a changed broker URL or AI
    service address plainly matters to it."""
    assert "config/settings.py" in task_dependency_files()


def test_a_worker_that_just_booted_is_up_to_date():
    record_boot()

    assert check().needs_restart is False


def test_a_changed_dependency_is_reported(tmp_path, monkeypatch):
    import json

    record_boot()
    stored = json.loads(_client().get(KEY))
    stored["documents/tasks.py"] = "a-different-hash"
    _client().set(KEY, json.dumps(stored))

    result = check()

    assert result.needs_restart is True
    assert "documents/tasks.py" in result.changed


def test_a_deleted_dependency_is_reported():
    import json

    record_boot()
    stored = json.loads(_client().get(KEY))
    stored["documents/gone_away.py"] = "whatever"
    _client().set(KEY, json.dumps(stored))

    assert "documents/gone_away.py" in check().changed


def test_no_recorded_boot_is_not_mistaken_for_up_to_date():
    """A worker that never started must not read as healthy."""
    _client().delete(KEY)

    result = check()

    assert result.missing_fingerprint is True
    assert result.needs_restart is False
