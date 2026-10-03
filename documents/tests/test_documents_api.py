import pytest

from documents.models import Document


@pytest.mark.django_db
def test_the_library_only_shows_your_own_documents(api, course, stranger):
    Document.objects.create(
        owner=stranger, title="Someone else's book", file="documents/other.pdf"
    )

    response = api.get("/api/documents/")

    assert response.status_code == 200
    assert [row["title"] for row in response.data] == ["Learning Python"]


@pytest.mark.django_db
def test_the_library_reports_generation_progress(api, course):
    response = api.get("/api/documents/")

    row = response.data[0]
    assert row["topics_total"] == 1
    assert row["topics_ready"] == 1
    assert row["syllabus_id"] == course["syllabus"].id


@pytest.mark.django_db
def test_uploading_queues_the_pipeline_and_returns_at_once(api, learner, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile

    dispatched: list[int] = []
    monkeypatch.setattr(
        "documents.views.process_document",
        type("Task", (), {"delay": staticmethod(lambda pk: dispatched.append(pk))}),
    )

    upload = SimpleUploadedFile("algebra.pdf", b"%PDF-1.7 fake", content_type="application/pdf")
    response = api.post("/api/documents/", {"file": upload}, format="multipart")

    assert response.status_code == 201
    # The title holds the filename's place until the syllabus supplies a real one.
    assert response.data["title"] == "algebra"
    assert response.data["status"] == Document.Status.PENDING
    document = Document.objects.get(pk=response.data["id"])
    assert document.owner == learner
    assert dispatched == [document.pk]


@pytest.mark.django_db
def test_a_non_pdf_is_refused(api, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile

    monkeypatch.setattr(
        "documents.views.process_document",
        type("Task", (), {"delay": staticmethod(lambda pk: None)}),
    )
    upload = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")

    response = api.post("/api/documents/", {"file": upload}, format="multipart")

    assert response.status_code == 400
