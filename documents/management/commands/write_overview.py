"""Fill in a course's summary and outcomes.

Books generated before the overview call existed have none. This writes one without
touching a single lesson, so a finished course gains its blurb for a fraction of a
cent rather than a re-run.
"""

from django.core.management.base import BaseCommand, CommandError

from documents.models import Document
from documents.tasks import _write_overview


class Command(BaseCommand):
    help = "Write the summary and outcomes for a document that has none."

    def add_arguments(self, parser) -> None:
        parser.add_argument("document_id", type=int)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rewrite a summary that is already there.",
        )

    def handle(self, *args, **options) -> None:
        try:
            document = Document.objects.get(pk=options["document_id"])
        except Document.DoesNotExist:
            raise CommandError(f"No document {options['document_id']}.")

        syllabus = getattr(document, "syllabus", None)
        if syllabus is None:
            raise CommandError(f"Document {document.pk} has no syllabus yet.")

        if syllabus.summary and not options["force"]:
            self.stdout.write(f"Already written: {syllabus.summary}")
            return

        _write_overview(document, syllabus)
        syllabus.refresh_from_db()

        if not syllabus.summary:
            raise CommandError("The overview call did not return anything. See the log above.")

        self.stdout.write(self.style.SUCCESS(syllabus.summary))
        for outcome in syllabus.outcomes:
            self.stdout.write(f"  - {outcome}")
