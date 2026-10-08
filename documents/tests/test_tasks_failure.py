from unittest.mock import patch

import pytest

from documents.models import Document, GenerationEvent
from documents.tasks import UNEXPECTED_GENERATION, UNEXPECTED_UPLOAD, _generate


@pytest.mark.django_db
def test_an_unexpected_error_before_the_syllabus_marks_the_upload_failed(course, caplog):
    document = course["document"]
    document.syllabus.delete()
    document.refresh_from_db()

    with patch("documents.tasks._prepare", side_effect=ValueError("something nobody caught")):
        _generate(task=None, document_id=document.pk, token="t")

    document.refresh_from_db()
    assert document.status == Document.Status.FAILED
    # Shown to a learner: a database constraint quoted verbatim tells them nothing.
    assert document.error == UNEXPECTED_UPLOAD
    assert document.events.filter(kind=GenerationEvent.Kind.FAILED).exists()
    # The real cause is in the log, with its traceback.
    assert "something nobody caught" in caplog.text


@pytest.mark.django_db
def test_an_unexpected_error_after_the_syllabus_says_generation(course):
    document = course["document"]

    with patch("documents.tasks._write_chapter", side_effect=RuntimeError("boom")):
        _generate(task=None, document_id=document.pk, token="t")

    document.refresh_from_db()
    assert document.status == Document.Status.FAILED
    assert document.error == UNEXPECTED_GENERATION


@pytest.mark.django_db
def test_a_retry_is_not_swallowed(course):
    from celery.exceptions import Retry

    with patch("documents.tasks._prepare", side_effect=Retry("retrying")):
        with pytest.raises(Retry):
            _generate(task=None, document_id=course["document"].pk, token="t")

    course["document"].refresh_from_db()
    # A retry is not a failure, and marking it one would stop the retry being tried.
    assert course["document"].status != Document.Status.FAILED
