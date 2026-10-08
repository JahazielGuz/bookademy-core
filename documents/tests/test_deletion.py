from pathlib import Path

import pytest

from curriculum.models import Chapter, Lesson, Syllabus, Topic
from documents.models import Document
from progress.models import StepCompletion


@pytest.mark.django_db
def test_deleting_a_document_takes_its_whole_course(api, course, learner):
    document = course["document"]
    StepCompletion.objects.create(
        user=learner, step=course["steps"][0], submitted_code="x = 1"
    )

    response = api.delete(f"/api/documents/{document.id}/")

    assert response.status_code == 204
    assert not Document.objects.filter(pk=document.pk).exists()
    # Everything generated under it goes too, or the database fills with orphans.
    assert not Syllabus.objects.exists()
    assert not Chapter.objects.exists()
    assert not Topic.objects.exists()
    assert not Lesson.objects.exists()
    assert not StepCompletion.objects.exists()


@pytest.mark.django_db
def test_deleting_a_document_removes_the_uploaded_pdf(api, course, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    document = course["document"]
    stored = Path(tmp_path) / "documents" / "learning-python.pdf"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"%PDF-1.4 pretend")

    api.delete(f"/api/documents/{document.id}/")

    # Django drops the row and leaves the file; a cleared library should not still
    # hold every book that was ever uploaded to it.
    assert not stored.exists()


@pytest.mark.django_db
def test_one_learner_cannot_delete_another_learners_book(api, course, django_user_model):
    other = django_user_model.objects.create_user(
        email="someone@example.com", password="a-long-enough-password"
    )
    course["document"].owner = other
    course["document"].save(update_fields=["owner"])

    response = api.delete(f"/api/documents/{course['document'].id}/")

    assert response.status_code == 404
    assert Document.objects.filter(pk=course["document"].pk).exists()
