"""One run per document, enforced rather than assumed.

A generation run costs real money and takes hours. Celery will redeliver a task it
believes was lost — and with `acks_late` and a broker visibility timeout of an hour,
"lost" means "still working". A run of this length is therefore redelivered on a
timer, and without a lock the redelivered copy starts again from chapter one while
the original is still going. Four copies of one book ran that way once; it is the
single most expensive bug this project has had.

So the document id is the lock. A second copy acquires nothing and exits, and the
only cost of a redelivery is the moment it takes to find that out.

The lock carries a token and is only released by the copy that holds it, so a run
that overshoots its expiry cannot release the lock a *different* copy has since
taken. It expires on its own, so a worker killed mid-run frees the document instead
of wedging it forever.
"""

import logging
from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Comfortably longer than one chapter, and refreshed as each chapter finishes, so a
# long book holds its lock without the expiry ever being reached while work is live.
LOCK_TTL_SECONDS = 3600

# Release only if the value still matches ours, as one step, so an expiry between the
# check and the delete cannot make us release someone else's lock.
RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.CELERY_BROKER_URL)


def key_for(document_id: int) -> str:
    return f"bookademy:document-run:{document_id}"


@contextmanager
def document_run(document_id: int) -> Iterator[str | None]:
    """Hold the run lock for one document.

    Yields a refresh token when this copy owns the run, or None when another copy
    already does — in which case the caller must do nothing at all.
    """
    client = _client()
    key = key_for(document_id)
    token = uuid4().hex

    if not client.set(key, token, nx=True, ex=LOCK_TTL_SECONDS):
        logger.warning(
            "document %s is already being generated; this copy is standing down",
            document_id,
        )
        yield None
        return

    try:
        yield token
    finally:
        try:
            client.eval(RELEASE, 1, key, token)
        except redis.RedisError:
            # Losing the release is survivable: the lock expires by itself.
            logger.exception("could not release the run lock for document %s", document_id)


def keep_held(document_id: int, token: str) -> bool:
    """Push the expiry back. Called as each chapter finishes, so the lock outlives a
    long book without ever being held by a copy that has stopped working."""
    client = _client()
    key = key_for(document_id)
    if client.get(key) != token.encode():
        return False
    client.expire(key, LOCK_TTL_SECONDS)
    return True
