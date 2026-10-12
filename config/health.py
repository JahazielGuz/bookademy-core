"""Liveness, not readiness.

Fly restarts a machine whose health check fails. A check that queried Postgres would
turn a database blip into a restart loop on an app that was otherwise fine, so this
only answers whether the process is up and serving.
"""

from django.http import JsonResponse


def health(request) -> JsonResponse:
    return JsonResponse({"status": "ok"})
