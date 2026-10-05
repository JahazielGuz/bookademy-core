"""A ceiling on what one book may cost.

Every other guard in this project either reduces cost or reports it. None of them
stop it. A run was once projected at $5, cost $20, and nothing in the system would
have intervened at any point — the only thing that would have helped was a brake.

The check runs before each model call against what the document has already been
billed, so a run can overshoot by at most the cost of the single call in flight —
under a cent at current prices. Checking afterwards would be a report; checking
beforehand is a limit.
"""

from django.conf import settings

from documents.models import Document, UsageRecord


class SpendLimitReached(Exception):
    """The document has cost as much as it is allowed to."""

    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(
            f"Stopped at the ${limit:.2f} limit for this book, having spent "
            f"${spent:.2f}. Everything generated so far is kept and can be used. "
            f"Raise DOCUMENT_SPEND_LIMIT_USD to continue."
        )


def spent_on(document: Document) -> float:
    """What this document has been billed, from recorded usage.

    Summed in Python rather than SQL because the price depends on which model each
    call used, and the per-call volume here is small enough that it does not matter.
    """
    return sum(record.cost_usd for record in UsageRecord.objects.filter(document=document))


def check_budget(document: Document) -> None:
    """Raise if this document has reached its ceiling."""
    limit = settings.DOCUMENT_SPEND_LIMIT_USD
    if limit <= 0:
        return

    spent = spent_on(document)
    if spent >= limit:
        raise SpendLimitReached(spent=spent, limit=limit)
