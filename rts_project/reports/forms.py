from django import forms
from django.utils import timezone

from .models import Department, Machine, ReturnToServiceReport


class _DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def format_value(self, value):
        if value in (None, ""):
            return ""
        if hasattr(value, "strftime"):
            return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")
        return value


def _style(fields):
    """Apply consistent CSS classes to a set of bound form fields."""
    for field in fields.values():
        css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        field.widget.attrs.setdefault("class", css)


class ClinicForm(forms.ModelForm):
    """Add a clinic that will appear as a selection option."""
    class Meta:
        model = Department
        fields = ["name", "code", "location"]
        labels = {"name": "Clinic name", "code": "Short code", "location": "Location"}

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
            "work_completed_at",
            "work_performed",
            "performed_by",
            "physics_status",
            "physics_evaluation",
            "physicist",
            "approved_by",
            "vendor_doc_url",
            "status",
        ]
        widgets = {
            "outage_start": _DateTimeInput(),
            "work_completed_at": _DateTimeInput(),
            "work_performed": forms.Textarea(attrs={"rows": 4}),
            "physics_evaluation": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "work_completed_at": "Work completed",
            "performed_by": "Work performed by",
            "physics_status": "Physics evaluation",
            "physics_evaluation": "Physics evaluation performed",
            "vendor_doc_url": "Vendor documentation link",
            "approved_by": "Return to service approved by",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Reorder so clinic appears before machine.
        order = list(self.fields)
        order.remove("clinic")
        order.insert(order.index("machine"), "clinic")
        self.order_fields(order)

        self.fields["machine"].empty_label = "Select a machine…"

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

        if cleaned.get("status") == ReturnToServiceReport.Status.RETURNED:
            if not cleaned.get("approved_by"):
                self.add_error(
                    "approved_by",
                    "An approver is required before a machine can be returned to service.",
                )
            if status == ReturnToServiceReport.PhysicsStatus.PENDING:
                self.add_error(
                    "physics_status",
                    "Physics evaluation is still pending; resolve it before returning to service.",
                )
        return cleaned
