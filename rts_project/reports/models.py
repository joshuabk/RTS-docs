"""Data model for machine return-to-service (RTS) reporting."""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Department(models.Model):
    """A radiation oncology department / treatment site."""
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(
        max_length=12, blank=True,
        help_text="Short identifier shown on reports, e.g. ROC-N.",
    )
    location = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Machine(models.Model):
    """A treatment or imaging machine that can be taken out of service."""

    class MachineType(models.TextChoices):
        LINAC = "linac", "Linear accelerator"
        CT_SIM = "ct_sim", "CT simulator"
        BRACHY = "brachy", "Brachytherapy unit"
        GAMMA = "gamma", "Gamma knife / SRS unit"
        ORTHO = "ortho", "Orthovoltage / superficial unit"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="machines",
    )
    machine_type = models.CharField(
        max_length=16, choices=MachineType.choices, default=MachineType.LINAC,
    )
    manufacturer = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["department__name", "name"]
        unique_together = [("department", "name")]

    def __str__(self):
        return f"{self.name} ({self.department.name})"


class ReturnToServiceReport(models.Model):
    """A record certifying a machine's return to clinical service after an outage."""

    class PhysicsStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PERFORMED = "performed", "Performed"
        PENDING = "pending", "Required - pending"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RETURNED = "returned", "Returned to service"

    # --- Which machine and where ---
    machine = models.ForeignKey(
        Machine, on_delete=models.PROTECT, related_name="rts_reports",
    )

    # --- Outage / work timeline ---
    outage_start = models.DateTimeField(
        null=True, blank=True,
        help_text="When the machine went out of service.",
    )
    work_completed_at = models.DateTimeField(
        help_text="When repair / maintenance work was completed.",
    )

    # --- What was worked on ---
    work_performed = models.TextField(
        help_text="Description of the fault and the repair / maintenance performed.",
    )
    performed_by = models.CharField(
        max_length=160, blank=True,
        help_text="Engineer or vendor who performed the work.",
    )

    # --- Physics evaluation ---
    physics_status = models.CharField(
        max_length=16, choices=PhysicsStatus.choices,
        default=PhysicsStatus.NOT_REQUIRED,
    )
    physics_evaluation = models.TextField(
        blank=True,
        help_text="Physics tests / measurements performed before return to service.",
    )
    physicist = models.CharField(
        max_length=160, blank=True,
        help_text="Medical physicist who performed / oversaw the evaluation.",
    )

    # --- Approval ---
    approved_by = models.CharField(
        max_length=160, blank=True,
        help_text="Name and role of the person approving return to service.",
    )
    approval_date = models.DateTimeField(null=True, blank=True)

    # --- Vendor documentation ---
    vendor_doc_url = models.CharField(
        "Vendor documentation link",max_length=160, blank=True,
        help_text="Link to the vendor's service report / documentation of the repair.",
    )

    # --- Workflow / audit ---
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="rts_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_completed_at", "-created_at"]
        verbose_name = "return-to-service report"

    def __str__(self):
        return f"RTS-{self.pk or 0:05d} · {self.machine.name}"

    @property
    def reference(self):
        """Human-facing report identifier."""
        return f"RTS-{self.pk:05d}" if self.pk else "RTS-NEW"

    @property
    def department(self):
        return self.machine.department

    def get_absolute_url(self):
        return reverse("reports:detail", args=[self.pk])

    @property
    def physics_required(self):
        return self.physics_status != self.PhysicsStatus.NOT_REQUIRED

    @property
    def is_returned(self):
        return self.status == self.Status.RETURNED

    def save(self, *args, **kwargs):
        # Stamp approval date the first time an approver is recorded.
        if self.approved_by and not self.approval_date:
            self.approval_date = timezone.now()
        super().save(*args, **kwargs)
