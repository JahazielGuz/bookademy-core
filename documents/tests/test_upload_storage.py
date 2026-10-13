from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile

from documents.models import Document
from documents.tasks import _discard_upload


def _with_file(document: Document) -> Document:
    document.file.save("book.pdf", ContentFile(b"%PDF-1.4 pretend"), save=True)
    return document


@pytest.mark.django_db
def test_the_upload_is_deleted_once_its_text_is_stored(course, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.DISCARD_UPLOAD_AFTER_READING = True
    document = _with_file(course["document"])
    stored = document.file.path

    _discard_upload(document)

    # Everything after extraction reads Document.pages, so the PDF is dead weight —
    # and on object storage dead weight is a monthly bill.
    assert not document.file
    assert document.pages == Document.objects.get(pk=document.pk).pages
    import os
    assert not os.path.exists(stored)


@pytest.mark.django_db
def test_the_upload_is_kept_on_local_disk(course, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.DISCARD_UPLOAD_AFTER_READING = False
    document = _with_file(course["document"])

    _discard_upload(document)

    # Locally the file costs nothing and is useful to have when debugging.
    assert document.file


@pytest.mark.django_db
def test_a_storage_failure_does_not_fail_the_document(course, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.DISCARD_UPLOAD_AFTER_READING = True
    document = _with_file(course["document"])

    with patch.object(type(document.file), "delete", side_effect=OSError("bucket down")):
        # The text is already saved and the course is about to be written; a storage
        # backend having a bad minute is not a reason to fail the document.
        _discard_upload(document)

    assert document.status != Document.Status.FAILED
