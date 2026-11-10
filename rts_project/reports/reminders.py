"""Overdue-report reminder emails.

A report is *overdue* when it has not reached "Returned to treatment" and its
outage started more than ``REMINDER_AFTER_DAYS`` ago. One email per clinic is
sent listing that clinic's overdue reports. ``REMINDER_EMAILS_ENABLED`` in
settings is the master on/off switch.
"""
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from .models import ReturnToServiceReport


def reminders_enabled():
    return bool(getattr(settings, "REMINDER_EMAILS_ENABLED", False))


def overdue_reports(now=None):
    """Reports not yet completed whose outage started > REMINDER_AFTER_DAYS ago."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=getattr(settings, "REMINDER_AFTER_DAYS", 7))
    return (
        ReturnToServiceReport.objects.exclude(status=ReturnToServiceReport.Status.RETURNED)
        .filter(outage_start__lte=cutoff)
        .select_related("machine", "machine__department")
        .order_by("machine__department__name", "outage_start")
    )


def reports_due_for_reminder(now=None):
    """Overdue reports that have not been reminded within REMINDER_REPEAT_DAYS."""
    now = now or timezone.now()
    repeat = timedelta(days=getattr(settings, "REMINDER_REPEAT_DAYS", 7))
    return [
        r for r in overdue_reports(now)
        if r.last_reminder_sent is None or r.last_reminder_sent <= now - repeat
    ]


def _recipients_for(clinic):
    seen, out = set(), []
    for e in list(clinic.notification_email_list) + list(getattr(settings, "REMINDER_DEFAULT_RECIPIENTS", [])):
        if e and e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return out


def _build_message(clinic, reports, now):
    site = getattr(settings, "SITE_URL", "").rstrip("/")
    lines = [
        f"The following return-to-service report{'s are' if len(reports) != 1 else ' is'} "
        f"still not completed for {clinic.name}:",
        "",
    ]
    for r in reports:
        days = (now - r.outage_start).days
        lines.append(f"  {r.reference}  {r.machine.name}")
        lines.append(f"      Outage started: {timezone.localtime(r.outage_start):%d %b %Y}  ({days} days ago)")
        lines.append(f"      Status: {r.get_status_display()}")
        lines.append(f"      Issue: {r.outage_issue.strip().splitlines()[0][:120] if r.outage_issue else '-'}")
        if site:
            lines.append(f"      {site}{r.get_absolute_url()}")
        lines.append("")
    lines.append("Please update the report (work performed, physics evaluation, approval) "
                 "and set its status to \"Returned to treatment\" once the machine is back in service.")
    lines.append("")
    lines.append("This is an automated reminder from the RTS Register.")
    subject = (getattr(settings, "REMINDER_SUBJECT_PREFIX", "") +
               f"{len(reports)} overdue report{'s' if len(reports) != 1 else ''} - {clinic.name}")
    return subject, "\n".join(lines)


def send_overdue_reminders(dry_run=False, force=False, now=None):
    """Send one reminder email per clinic.

    Returns a summary dict: {"enabled", "sent", "skipped_no_recipients",
    "reports", "emails": [(clinic, recipients, n_reports, subject)], "errors"}.
    ``dry_run`` builds everything but sends nothing and records nothing.
    ``force`` ignores the repeat interval (re-reminds every overdue report).
    """
    now = now or timezone.now()
    enabled = reminders_enabled()
    reports = list(overdue_reports(now)) if force else reports_due_for_reminder(now)

    by_clinic = defaultdict(list)
    for r in reports:
        by_clinic[r.machine.department].append(r)

    summary = {"enabled": enabled, "sent": 0, "skipped_no_recipients": 0,
               "reports": len(reports), "emails": [], "errors": []}
    will_send = enabled and not dry_run
    connection = get_connection() if will_send else None

    for clinic, items in by_clinic.items():
        recipients = _recipients_for(clinic)
        subject, body = _build_message(clinic, items, now)
        if not recipients:
            summary["skipped_no_recipients"] += 1
            summary["emails"].append((clinic, [], len(items), subject))
            continue
        summary["emails"].append((clinic, recipients, len(items), subject))
        if not will_send:
            continue
        try:
            EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, recipients,
                         connection=connection).send()
            summary["sent"] += 1
            ReturnToServiceReport.objects.filter(pk__in=[r.pk for r in items]).update(
                last_reminder_sent=now
            )
        except Exception as exc:  # SMTP problems should never crash the caller
            summary["errors"].append(f"{clinic.name}: {exc}")
    return summary
