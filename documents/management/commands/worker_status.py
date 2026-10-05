"""Say whether the running worker is out of date, and only then."""

from django.core.management.base import BaseCommand

from documents.staleness import check


class Command(BaseCommand):
    help = "Report whether the Celery worker is running code that has since changed."

    def handle(self, *args, **options) -> None:
        result = check()

        if result.missing_fingerprint:
            self.stdout.write(
                self.style.WARNING(
                    "No worker has recorded a boot. Either none is running, or it "
                    "started before this check existed — restart it once."
                )
            )
            return

        if not result.needs_restart:
            self.stdout.write(
                self.style.SUCCESS(
                    "Worker is up to date. Nothing its tasks depend on has changed "
                    "since it booted, so a restart would achieve nothing."
                )
            )
            return

        self.stdout.write(
            self.style.ERROR(
                f"Worker is STALE — {len(result.changed)} file(s) its tasks depend on "
                f"have changed since it booted:"
            )
        )
        for path in result.changed:
            self.stdout.write(f"   {path}")
        self.stdout.write(
            "\nRestart it for these to take effect. If a generation run is in "
            "progress, the run is safe to let finish first — it is unaffected by "
            "the edits."
        )
