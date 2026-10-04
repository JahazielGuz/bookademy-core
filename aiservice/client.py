"""Thin HTTP client for bookademy-ai.

Only Celery tasks call this. It raises two kinds of error on purpose, because the
caller's decision differs: AIServiceError is worth retrying, AIServiceRefused is not.
"""

from typing import Any

import httpx
from django.conf import settings


class AIServiceError(Exception):
    """Transport or provider failure. Retry."""


class AIServiceRefused(Exception):
    """The model declined, or returned something that did not fit the schema.
    Retrying sends the identical request, so do not."""


def _post(path: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{settings.AI_SERVICE_URL}{path}"
    headers = {"X-Service-Token": settings.SERVICE_TOKEN}
    try:
        response = httpx.post(
            url, headers=headers, timeout=settings.AI_SERVICE_TIMEOUT_SECONDS, **kwargs
        )
    except httpx.HTTPError as exc:
        raise AIServiceError(f"Could not reach the AI service: {exc}") from exc

    if response.status_code == 422:
        raise AIServiceRefused(response.text)
    if response.status_code >= 400:
        raise AIServiceError(f"AI service returned {response.status_code}: {response.text}")
    return response.json()


def read_document(*, filename: str, content: bytes) -> dict[str, Any]:
    """Structure and per-page text. No model is involved in this call."""
    return _post("/v1/documents", files={"file": (filename, content, "application/pdf")})


def chapter_topics(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/v1/chapter-topics", json=payload)


def topic_content(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/v1/topic-content", json=payload)
