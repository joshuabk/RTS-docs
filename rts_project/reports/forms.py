from django import forms
from django.conf import settings
from django.utils import timezone

from .models import Department, Machine, ReturnToServiceReport


class _DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def format_value(self, value):
        if value in (None, ""):
            return ""
        if hasattr(value, "strftime"):
            # localtime() only accepts aware datetimes; render naive ones as-is.
            if timezone.is_aware(value):
                value = timezone.localtime(value)
            return value.strftime("%Y-%m-%dT%H:%M")
        return value


def _style(fields):
    """Apply consistent CSS classes to a set of bound form fields."""
    for field in fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            css = "form-check"
        elif isinstance(field.widget, forms.Select):
            css = "form-select"
        else:
            css = "form-control"
        field.widget.attrs.setdefault("class", css)


class ClinicForm(forms.ModelForm):
    """Add a clinic that will appear as a selection option."""
    class Meta:
        model = Department
        fields = ["name", "code", "location", "notification_emails"]
        labels = {"name": "Clinic name", "code": "Short code", "location": "Location",
                  "notification_emails": "Reminder email recipients"}
        widgets = {"notification_emails": forms.Textarea(attrs={"rows": 2, "placeholder": "name@northside.com, other@northside.com"})}

    def clean_notification_emails(self):
        from django.core.validators import validate_email
        raw = self.cleaned_data.get("notification_emails", "")
        emails = [e.strip() for e in raw.replace(";", ",").replace("\n", ",").split(",") if e.strip()]
        for e in emails:
            try:
                validate_email(e)
            except forms.ValidationError:
                raise forms.ValidationError(f"'{e}' is not a valid email address.")
        return ", ".join(emails)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)


class MachineForm(forms.ModelForm):
    """Add a machine and associate it with exactly one clinic."""
    class Meta:
        model = Machine
        fields = [
            "name", "department", "machine_type",
            "manufacturer", "model", "serial_number",
        ]
        labels = {"department": "Clinic"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.all()
        self.fields["department"].empty_label = "Select a clinic…"
        _style(self.fields)


class _PdfFileInput(forms.ClearableFileInput):
    """File input without Django's default "Currently: <media link>" block.

    The form template renders the current file itself, linking to the
    protected download view, together with a "Remove" checkbox."""

    def format_value(self, value):
        return None


class ReturnToServiceReportForm(forms.ModelForm):
    # UI helper: choose the clinic first, which filters the machine list.
    clinic = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        empty_label="Select a clinic…",
        label="Clinic",
    )

    class Meta:
        model = ReturnToServiceReport
        fields = [
            "clinic",
            "machine",
            "outage_start",
            "outage_issue",
            "work_completed_at",
            "work_performed",
            "performed_by",
            "physics_status",
            "physics_evaluation",
            "physicist",
            "approved_by",
            "vendor_report_received",
            "vendor_report_url",
            "vendor_report_file",
            "status",
        ]
        widgets = {
            "outage_start": _DateTimeInput(),
            "work_completed_at": _DateTimeInput(),
            "outage_issue": forms.Textarea(attrs={"rows": 3}),
            "work_performed": forms.Textarea(attrs={"rows": 4}),
            "physics_evaluation": forms.Textarea(attrs={"rows": 4}),
            "vendor_report_url": forms.URLInput(attrs={"placeholder": "https://…"}),
            "vendor_report_file": _PdfFileInput(attrs={"accept": "application/pdf,.pdf"}),
        }
        labels = {
            "outage_issue": "Outage issue",
            "work_completed_at": "Work completed",
            "performed_by": "Work performed by",
            "physics_status": "Physics evaluation",
            "physics_evaluation": "Physics evaluation performed",
            "physicist": "Evaluator",
            "vendor_report_received": "Vendor report received",
            "vendor_report_url": "Vendor report link",
            "vendor_report_file": "Vendor report (PDF)",
            "approved_by": "Approving physicist",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Reorder so clinic appears before machine.
        order = list(self.fields)
        order.remove("clinic")
        order.insert(order.index("machine"), "clinic")
        self.order_fields(order)

        self.fields["machine"].empty_label = "Select a machine…"

        # A report can be opened as soon as the machine goes down. Only the
        # clinic, machine, outage start and outage issue are required up front;
        # everything else is filled in as the repair progresses.
        # (Select fields such as status keep their defaults and stay required.)
        for name in (
            "work_completed_at", "work_performed", "performed_by",
            "physics_evaluation", "physicist", "approved_by", "vendor_report_received",
            "vendor_report_url", "vendor_report_file",
        ):
            self.fields[name].required = False
        for name in ("clinic", "machine", "outage_start", "outage_issue"):
            self.fields[name].required = True

        # Determine which clinic is in play, so the machine <select> only
        # shows that clinic's machines (works even with JavaScript disabled).
        clinic_id = None
        if self.is_bound:
            clinic_id = self.data.get("clinic") or None
        elif self.instance.pk:
            clinic_id = self.instance.machine.department_id
            self.fields["clinic"].initial = clinic_id

        if clinic_id:
            self.fields["machine"].queryset = Machine.objects.filter(
                department_id=clinic_id
            ).select_related("department")
        else:
            self.fields["machine"].queryset = Machine.objects.none()

        _style(self.fields)

    def clean(self):
        cleaned = super().clean()

        clinic = cleaned.get("clinic")
        machine = cleaned.get("machine")
        if clinic and machine and machine.department_id != clinic.id:
            self.add_error(
                "machine",
                "That machine does not belong to the selected clinic.",
            )

        start = cleaned.get("outage_start")
        done = cleaned.get("work_completed_at")
        if start and done and done < start:
            self.add_error(
                "work_completed_at",
                "Work completion cannot be earlier than the start of the outage.",
            )

        status = cleaned.get("physics_status")
        evaluation = cleaned.get("physics_evaluation")
        if status == ReturnToServiceReport.PhysicsStatus.PERFORMED and not evaluation:
            self.add_error(
                "physics_evaluation",
                "Describe the physics evaluation that was performed.",
            )

        Status = ReturnToServiceReport.Status
        report_status = cleaned.get("status")
        if report_status in (Status.SERVICE_COMPLETE, Status.RETURNED):
            if not done:
                self.add_error(
                    "work_completed_at",
                    "Record when the work was completed before marking service complete.",
                )
            if not cleaned.get("work_performed"):
                self.add_error(
                    "work_performed",
                    "Describe the work performed before marking service complete.",
                )
        if report_status == Status.RETURNED:
            if not cleaned.get("approved_by"):
                self.add_error(
                    "approved_by",
                    "An approver is required before a machine can be returned to treatment.",
                )
            if status == ReturnToServiceReport.PhysicsStatus.PENDING:
                self.add_error(
                    "physics_status",
                    "Physics evaluation is still pending; resolve it before returning to treatment.",
                )
        return cleaned

    def clean_vendor_report_file(self):
        f = self.cleaned_data.get("vendor_report_file")
        if f and hasattr(f, "size"):
            limit_mb = getattr(settings, "MAX_UPLOAD_MB", 20)
            if f.size > limit_mb * 1024 * 1024:
                raise forms.ValidationError(f"The PDF must be smaller than {limit_mb} MB.")
            ctype = getattr(f, "content_type", "") or ""
            if ctype and ctype not in ("application/pdf", "application/x-pdf", "application/octet-stream"):
                raise forms.ValidationError("Only PDF files can be uploaded.")
        return f

    def clean(self):
        cleaned = super().clean()
        # Attaching a link or a PDF means the vendor report has been received.
        if cleaned.get("vendor_report_url") or cleaned.get("vendor_report_file"):
            cleaned["vendor_report_received"] = True
        return cleaned
