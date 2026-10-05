"""Recorded spend.

This exists because a run was predicted at $5 and cost $20, and nothing in the system
could say where the difference went — because nothing recorded what each call used.
"""

import pytest

from documents.models import Document, UsageRecord


@pytest.fixture
def document(learner):
    return Document.objects.create(owner=learner, title="A book", file="b.pdf")


def record(document, **kwargs):
    defaults = dict(
        kind=UsageRecord.Kind.CONTENT,
        model="gpt-5-mini",
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
    )
    return UsageRecord.objects.create(document=document, **{**defaults, **kwargs})


@pytest.mark.django_db
def test_cost_is_priced_from_the_table(document):
    # 1M fresh input at $0.25 and 1M output at $2.00.
    usage = record(document, input_tokens=1_000_000, output_tokens=1_000_000)

    assert usage.cost_usd == pytest.approx(2.25)


@pytest.mark.django_db
def test_cached_input_is_not_billed_as_fresh_input(document):
    """Cached tokens are a tenth of the price; counting them as fresh would overstate
    every total this system reports."""
    usage = record(document, input_tokens=1_000_000, cached_input_tokens=1_000_000)

    assert usage.cost_usd == pytest.approx(0.025)


@pytest.mark.django_db
def test_partially_cached_input_splits_correctly(document):
    usage = record(document, input_tokens=1_000_000, cached_input_tokens=600_000)

    # 400k fresh at $0.25/M + 600k cached at $0.025/M
    assert usage.cost_usd == pytest.approx(0.1 + 0.015)


@pytest.mark.django_db
def test_an_unpriced_model_reports_zero_rather_than_guessing(document):
    usage = record(document, model="some-model-we-have-no-price-for", output_tokens=1_000_000)

    assert usage.cost_usd == 0.0


@pytest.mark.django_db
def test_every_call_is_counted_including_ones_that_produced_nothing(api, document):
    """A call that returned unusable content was still billed. A total that counts
    only successful topics is the total that made $20 look like $5."""
    record(document, output_tokens=500_000)
    record(document, output_tokens=500_000, topic_title="this one failed validation")

    response = api.get("/api/documents/")
    row = next(r for r in response.data if r["id"] == document.id)

    assert row["calls_made"] == 2
    assert row["cost_usd"] == pytest.approx(2.0)


@pytest.mark.django_db
def test_a_document_with_no_calls_costs_nothing(api, document):
    response = api.get("/api/documents/")
    row = next(r for r in response.data if r["id"] == document.id)

    assert row["cost_usd"] == 0.0
    assert row["calls_made"] == 0
