"""Email clinics about reports that are still not completed.

Run daily (Windows Task Scheduler / cron):
    python manage.py send_overdue_reminders

Options:
    --dry-run   show what would be sent, send nothing
    --force     ignore the repeat interval and remind every overdue report
"""
from django.core.management.base import BaseCommand

from reports.reminders import reminders_enabled, send_overdue_reminders


class Command(BaseCommand):
    help = "Send reminder emails for return-to-service reports that are overdue."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **opts):
        if not reminders_enabled():
            self.stdout.write(self.style.WARNING(
                "REMINDER_EMAILS_ENABLED is False in settings - nothing will be sent (dry run)."))
        result = send_overdue_reminders(dry_run=opts["dry_run"], force=opts["force"])
        if not result["emails"]:
            self.stdout.write("No overdue reports due for a reminder.")
            return
        for clinic, recipients, n, subject in result["emails"]:
            to = ", ".join(recipients) if recipients else "(no recipients configured - skipped)"
            self.stdout.write(f"{clinic.name}: {n} report(s) -> {to}")
        for err in result["errors"]:
            self.stderr.write(self.style.ERROR(err))
        self.stdout.write(self.style.SUCCESS(
            f"Sent {result['sent']} email(s); {result['skipped_no_recipients']} clinic(s) had no recipients."))
