from unittest.mock import patch

import pytest

from curriculum.models import Syllabus
from documents.models import UsageRecord
from documents.tasks import _write_overview

RESPONSE = {
    "summary": "Build full-stack React applications with TypeScript.",
    "outcomes": ["Write typed React components", "Test a Redux store"],
    "usage": {
        "model": "gpt-4o-mini",
        "input_tokens": 900,
        "cached_input_tokens": 0,
        "output_tokens": 80,
    },
}


@pytest.mark.django_db
def test_the_overview_is_stored_and_billed(course):
    document = course["document"]
    syllabus = Syllabus.objects.get(document=document)

    with patch("documents.tasks.request_overview", return_value=RESPONSE):
        _write_overview(document, syllabus)

    syllabus.refresh_from_db()
    assert syllabus.summary == RESPONSE["summary"]
    assert syllabus.outcomes == RESPONSE["outcomes"]

    record = UsageRecord.objects.get(document=document, kind=UsageRecord.Kind.OVERVIEW)
    assert record.output_tokens == 80


@pytest.mark.django_db
def test_a_failed_overview_does_not_fail_the_document(course):
    from aiservice.client import AIServiceError

    document = course["document"]
    syllabus = Syllabus.objects.get(document=document)

    with patch("documents.tasks.request_overview", side_effect=AIServiceError("down")):
        # The cheapest call in the run is not worth failing a course over.
        _write_overview(document, syllabus)

    syllabus.refresh_from_db()
    assert syllabus.summary == ""


@pytest.mark.django_db
def test_the_syllabus_endpoint_carries_the_overview(api, course):
    syllabus = Syllabus.objects.get(document=course["document"])
    syllabus.summary = RESPONSE["summary"]
    syllabus.outcomes = RESPONSE["outcomes"]
    syllabus.save(update_fields=["summary", "outcomes"])

    response = api.get(f"/api/documents/{course['document'].id}/syllabus/")

    assert response.data["summary"] == RESPONSE["summary"]
    assert response.data["outcomes"] == RESPONSE["outcomes"]
