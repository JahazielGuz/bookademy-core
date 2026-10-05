"""One run per document.

These exist because the alternative was measured: four copies of one book ran
concurrently and spent four times what the book should have cost.
"""

import pytest

from documents.locks import document_run, keep_held, key_for


@pytest.fixture(autouse=True)
def clean_lock():
    """Leave no lock behind, so a failure here cannot wedge the next test."""
    from documents.locks import _client

    yield
    _client().delete(key_for(4242), key_for(4243))


def test_one_copy_gets_the_lock():
    with document_run(4242) as token:
        assert token is not None


def test_a_second_copy_gets_nothing_while_the_first_holds_it():
    with document_run(4242) as first:
        assert first is not None
        with document_run(4242) as second:
            assert second is None


def test_the_lock_is_released_when_the_run_ends():
    with document_run(4242) as token:
        assert token is not None

    with document_run(4242) as again:
        assert again is not None


def test_a_different_document_is_not_blocked():
    """Two books generate at once; it is two copies of one book that must not."""
    with document_run(4242) as first:
        with document_run(4243) as other:
            assert first is not None
            assert other is not None


def test_the_lock_is_released_even_when_the_run_raises():
    with pytest.raises(RuntimeError):
        with document_run(4242):
            raise RuntimeError("generation blew up")

    with document_run(4242) as again:
        assert again is not None


def test_a_holder_can_push_its_expiry_back():
    with document_run(4242) as token:
        assert keep_held(4242, token) is True


def test_a_stale_copy_cannot_push_back_a_lock_it_no_longer_holds():
    """A run that overshot its expiry must discover that, not carry on alongside
    whoever took the lock after it."""
    with document_run(4242) as token:
        assert keep_held(4242, "a-different-copys-token") is False
        assert token is not None


def test_a_stale_copy_cannot_release_a_lock_someone_else_took():
    from documents.locks import _client

    client = _client()
    client.set(key_for(4242), "someone-elses-token", ex=60)

    # A copy whose own lock expired runs its release; it must not take out the lock
    # that has since been granted to another copy.
    with document_run(4242) as token:
        assert token is None

    assert client.get(key_for(4242)) == b"someone-elses-token"
