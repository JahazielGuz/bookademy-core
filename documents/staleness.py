"""Does the running worker need restarting?

A Celery worker imports its code once at boot and never looks at the files again, so
editing the monolith cannot disturb a run in progress — and equally, a change the
worker needs will not reach it until someone restarts it. Both halves of that have
cost this project something: a worker left running on week-old code called an endpoint
that no longer existed, and a worker restarted for no reason is a restart that could
have interrupted a run.

So the worker records what it actually imported, and this answers the question from
that record rather than from anyone's memory of which files matter. The set is
collected from `sys.modules` at boot, which means it stays correct on its own — a new
import inside a task's dependency tree is picked up without anyone maintaining a list.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import redis
from django.conf import settings

KEY = "bookademy:worker-fingerprint"


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.CELERY_BROKER_URL)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# Settings reach the worker through django.conf rather than by direct import, so they
# are seeded explicitly: a changed broker URL or AI service address matters to it.
ALWAYS = ("config.settings", "config.celery")


def _dependency_closure(start: set[str]) -> set[str]:
    """Every module the given modules reach, directly or transitively.

    Walked with a queue rather than recursion, because an import graph has cycles and
    a deep one would otherwise blow the stack.

    Module references are followed two ways: a module in a namespace (`import x`) and
    the defining module of anything else in it (`from x import Thing` leaves no module
    behind, but `Thing.__module__` names it).
    """
    import inspect
    import sys

    seen: set[str] = set()
    queue = list(start)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)

        module = sys.modules.get(name)
        if module is None:
            continue
        for value in vars(module).values():
            found = value.__name__ if inspect.ismodule(value) else getattr(value, "__module__", None)
            if isinstance(found, str) and found not in seen:
                queue.append(found)
    return seen


def task_dependency_files() -> dict[str, str]:
    """The project files the worker's tasks actually depend on, with their hashes.

    Deliberately not "everything the process imported". A worker calls
    `django.setup()`, which loads the URL conf and therefore every view, serializer
    and admin module in the project — none of which a task touches. Fingerprinting
    all of that would report the worker as stale whenever anyone edited a web
    template, which is the opposite of useful.
    """
    from config.celery import app

    # Task discovery is lazy: a task registers when its module is imported, which a
    # worker does at boot and nothing else necessarily does. Forcing it here makes
    # this answer the same question from any process.
    app.loader.import_default_modules()

    roots = {
        task.__module__
        for name, task in app.tasks.items()
        if not name.startswith("celery.")
    }
    roots.update(ALWAYS)

    import sys

    root = Path(settings.BASE_DIR).resolve()
    found: dict[str, str] = {}
    for name in _dependency_closure(roots):
        module = sys.modules.get(name)
        file = getattr(module, "__file__", None)
        if not file:
            continue
        path = Path(file).resolve()
        if root not in path.parents or ".venv" in path.parts:
            continue
        try:
            found[str(path.relative_to(root))] = digest(path)
        except OSError:
            continue
    return found


def record_boot() -> None:
    """Store what this worker's tasks depend on. Called once, as it comes up."""
    _client().set(KEY, json.dumps(task_dependency_files()))


@dataclass
class Staleness:
    changed: list[str]
    missing_fingerprint: bool

    @property
    def needs_restart(self) -> bool:
        return bool(self.changed)


def check() -> Staleness:
    """Compare the files on disk against what the worker actually loaded."""
    raw = _client().get(KEY)
    if raw is None:
        return Staleness(changed=[], missing_fingerprint=True)

    recorded: dict[str, str] = json.loads(raw)
    root = Path(settings.BASE_DIR).resolve()

    changed = []
    for relative, was in recorded.items():
        path = root / relative
        if not path.exists():
            changed.append(relative)
            continue
        if digest(path) != was:
            changed.append(relative)
    return Staleness(changed=sorted(changed), missing_fingerprint=False)
