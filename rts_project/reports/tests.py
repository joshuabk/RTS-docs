from django.test import TestCase
from django.urls import reverse

# Create your tests here.


class ManageAdminGateTests(TestCase):
    """The clinics & machines pages require the separate admin sign-in."""

    def test_manage_redirects_to_admin_login(self):
        resp = self.client.get(reverse("reports:manage"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(reverse("reports:manage_login")))

    def test_add_pages_redirect_to_admin_login(self):
        for name in ("reports:clinic_create", "reports:machine_create"):
            resp = self.client.post(reverse(name), {"name": "x"})
            self.assertEqual(resp.status_code, 302, name)
            self.assertTrue(resp["Location"].startswith(reverse("reports:manage_login")), name)

    def test_wrong_password_rejected(self):
        resp = self.client.post(
            reverse("reports:manage_login"),
            {"username": "RTSadmin", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please try again.")
        self.assertEqual(self.client.get(reverse("reports:manage")).status_code, 302)

    def test_correct_login_grants_access_and_logout_revokes(self):
        resp = self.client.post(
            reverse("reports:manage_login") + "?next=" + reverse("reports:manage"),
            {"username": "RTSadmin", "password": "northsiderts", "next": reverse("reports:manage")},
        )
        self.assertRedirects(resp, reverse("reports:manage"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("reports:manage")).status_code, 200)
        self.client.post(reverse("reports:manage_logout"))
        self.assertEqual(self.client.get(reverse("reports:manage")).status_code, 302)


import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .models import Department, Machine, ReturnToServiceReport

_MEDIA = tempfile.mkdtemp(prefix="rts-test-media-")
_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@override_settings(MEDIA_ROOT=_MEDIA, REQUIRE_LOGIN=False)
class VendorReportAttachmentTests(TestCase):
    """A report can carry a link to the vendor report and/or an uploaded PDF."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.dept = Department.objects.create(name="Northside", code="NS")
        self.machine = Machine.objects.create(
            name="TrueBeam 1", department=self.dept, machine_type=Machine.MachineType.LINAC
        )

    def _post_data(self, **extra):
        data = {
            "clinic": self.dept.pk,
            "machine": self.machine.pk,
            "outage_start": "2026-11-10 08:00",
            "outage_issue": "MLC fault",
            "physics_status": ReturnToServiceReport.PhysicsStatus.NOT_REQUIRED,
            "status": ReturnToServiceReport.Status.PENDING,
        }
        data.update(extra)
        return data

    def test_link_saves_and_marks_received(self):
        resp = self.client.post(
            reverse("reports:create"),
            self._post_data(vendor_report_url="https://vendor.example.com/report/123"),
        )
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        report = ReturnToServiceReport.objects.get()
        self.assertEqual(report.vendor_report_url, "https://vendor.example.com/report/123")
        self.assertTrue(report.vendor_report_received)
        detail = self.client.get(report.get_absolute_url())
        self.assertContains(detail, "https://vendor.example.com/report/123")

    def test_pdf_upload_saves_and_can_be_downloaded(self):
        pdf = SimpleUploadedFile("service_report.pdf", _PDF_BYTES, content_type="application/pdf")
        resp = self.client.post(reverse("reports:create"), self._post_data(vendor_report_file=pdf))
        self.assertEqual(resp.status_code, 302)
        report = ReturnToServiceReport.objects.get()
        self.assertTrue(report.vendor_report_file.name.endswith(".pdf"))
        self.assertTrue(report.vendor_report_received)

        dl = self.client.get(reverse("reports:vendor_report", args=[report.pk]))
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(dl.streaming_content), _PDF_BYTES)

    def test_non_pdf_upload_is_rejected(self):
        bad = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        resp = self.client.post(reverse("reports:create"), self._post_data(vendor_report_file=bad))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("vendor_report_file", resp.context["form"].errors)
        self.assertEqual(ReturnToServiceReport.objects.count(), 0)

    def test_download_404_when_no_file(self):
        resp = self.client.post(reverse("reports:create"), self._post_data())
        self.assertEqual(resp.status_code, 302)
        report = ReturnToServiceReport.objects.get()
        self.assertEqual(self.client.get(reverse("reports:vendor_report", args=[report.pk])).status_code, 404)

    def test_report_pdf_export_mentions_vendor_report(self):
        self.client.post(
            reverse("reports:create"),
            self._post_data(vendor_report_url="https://vendor.example.com/r/9"),
        )
        report = ReturnToServiceReport.objects.get()
        resp = self.client.get(reverse("reports:pdf", args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


from datetime import timedelta

from django.core import mail
from django.utils import timezone

from .reminders import send_overdue_reminders, overdue_reports


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMINDER_EMAILS_ENABLED=True, REMINDER_AFTER_DAYS=7, REMINDER_REPEAT_DAYS=7,
    REMINDER_DEFAULT_RECIPIENTS=["physics@example.com"], REQUIRE_LOGIN=False,
    DEFAULT_FROM_EMAIL="rts@example.com",
)
class OverdueReminderTests(TestCase):
    def setUp(self):
        self.clinic = Department.objects.create(
            name="Northside", code="NS", notification_emails="eng@example.com, lead@example.com"
        )
        self.other = Department.objects.create(name="Westside", code="WS")  # no recipients
        self.m1 = Machine.objects.create(name="TrueBeam 1", department=self.clinic)
        self.m2 = Machine.objects.create(name="CT Sim", department=self.other)
        self.now = timezone.now()

    def _report(self, machine, days_ago, status=ReturnToServiceReport.Status.PENDING):
        return ReturnToServiceReport.objects.create(
            machine=machine, outage_start=self.now - timedelta(days=days_ago),
            outage_issue="Fault", status=status,
        )

    def test_only_old_incomplete_reports_are_overdue(self):
        old_open = self._report(self.m1, 10)
        self._report(self.m1, 3)                                                     # too recent
        self._report(self.m1, 20, ReturnToServiceReport.Status.RETURNED)             # complete
        self.assertEqual(list(overdue_reports(self.now)), [old_open])

    def test_one_email_per_clinic_with_clinic_and_default_recipients(self):
        r1 = self._report(self.m1, 10)
        r2 = self._report(self.m1, 15)
        self._report(self.m2, 12)  # Westside has no clinic recipients -> default list only
        result = send_overdue_reminders(now=self.now)
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["skipped_no_recipients"], 0)
        self.assertEqual(len(mail.outbox), 2)
        west = next(m for m in mail.outbox if "Westside" in m.subject)
        self.assertEqual(west.to, ["physics@example.com"])
        msg = next(m for m in mail.outbox if "Northside" in m.subject)
        self.assertEqual(sorted(msg.to), ["eng@example.com", "lead@example.com", "physics@example.com"])
        self.assertIn("2 overdue reports - Northside", msg.subject)
        self.assertIn(r1.reference, msg.body)
        self.assertIn(r2.reference, msg.body)
        for r in (r1, r2):
            r.refresh_from_db()
            self.assertIsNotNone(r.last_reminder_sent)

    @override_settings(REMINDER_DEFAULT_RECIPIENTS=[])
    def test_clinic_without_any_recipients_is_skipped(self):
        self._report(self.m2, 12)
        result = send_overdue_reminders(now=self.now)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped_no_recipients"], 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_not_re_reminded_until_repeat_interval_passes(self):
        self._report(self.m1, 10)
        send_overdue_reminders(now=self.now)
        send_overdue_reminders(now=self.now + timedelta(days=2))
        self.assertEqual(len(mail.outbox), 1)
        send_overdue_reminders(now=self.now + timedelta(days=8))
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(REMINDER_EMAILS_ENABLED=False)
    def test_switch_off_sends_nothing(self):
        self._report(self.m1, 10)
        result = send_overdue_reminders(now=self.now)
        self.assertFalse(result["enabled"])
        self.assertEqual(result["reports"], 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_sends_nothing_and_records_nothing(self):
        r = self._report(self.m1, 10)
        send_overdue_reminders(dry_run=True, now=self.now)
        self.assertEqual(len(mail.outbox), 0)
        r.refresh_from_db()
        self.assertIsNone(r.last_reminder_sent)

    def test_send_now_button_requires_admin_and_sends(self):
        self._report(self.m1, 10)
        resp = self.client.post(reverse("reports:send_reminders"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(reverse("reports:manage_login")))
        self.assertEqual(len(mail.outbox), 0)

        self.client.post(reverse("reports:manage_login"),
                         {"username": "RTSadmin", "password": "northsiderts"})
        resp = self.client.post(reverse("reports:send_reminders"), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resp, "Sent 1 reminder email")

    def test_clinic_form_validates_recipient_emails(self):
        from .forms import ClinicForm
        bad = ClinicForm({"name": "X", "notification_emails": "not-an-email"})
        self.assertFalse(bad.is_valid())
        good = ClinicForm({"name": "X", "notification_emails": "a@example.com\nb@example.com;c@example.com"})
        self.assertTrue(good.is_valid(), good.errors)
        self.assertEqual(good.cleaned_data["notification_emails"], "a@example.com, b@example.com, c@example.com")
