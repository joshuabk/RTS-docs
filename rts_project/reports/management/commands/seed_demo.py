from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from reports.models import Department, Machine, ReturnToServiceReport


class Command(BaseCommand):
    help = "Create demo departments, machines, a sample report, and an admin user."

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "changeme123")
            self.stdout.write(self.style.SUCCESS("Created superuser admin / changeme123"))

        north, _ = Department.objects.get_or_create(
            name="North Campus Radiation Oncology",
            defaults={"code": "ROC-N", "location": "North Campus, Level 1"},
        )
        south, _ = Department.objects.get_or_create(
            name="South Campus Radiation Oncology",
            defaults={"code": "ROC-S", "location": "South Campus, Basement"},
        )

        tb, _ = Machine.objects.get_or_create(
            name="TrueBeam 2", department=north,
            defaults=dict(machine_type=Machine.MachineType.LINAC,
                          manufacturer="Varian", model="TrueBeam",
                          serial_number="TB-2210-0457"),
        )
        Machine.objects.get_or_create(
            name="Halcyon 1", department=south,
            defaults=dict(machine_type=Machine.MachineType.LINAC,
                          manufacturer="Varian", model="Halcyon",
                          serial_number="HAL-1903-1182"),
        )
        Machine.objects.get_or_create(
            name="CT Sim A", department=north,
            defaults=dict(machine_type=Machine.MachineType.CT_SIM,
                          manufacturer="Siemens", model="SOMATOM go.Open Pro"),
        )

        now = timezone.now()
        if not ReturnToServiceReport.objects.exists():
            ReturnToServiceReport.objects.create(
                machine=tb,
                outage_start=now - timedelta(days=1, hours=6),
                work_completed_at=now - timedelta(hours=3),
                work_performed=(
                    "Multileaf collimator carriage motor replaced after intermittent "
                    "interlock faults. Carriage recalibrated and travel verified."
                ),
                performed_by="Varian FSE - J. Alvarez",
                physics_status=ReturnToServiceReport.PhysicsStatus.PERFORMED,
                physics_evaluation=(
                    "MLC picket fence and leaf-position checks within tolerance. "
                    "Output constancy verified at 6X/10X. Star-shot and MV imaging QA passed."
                ),
                physicist="Dr. R. Okafor, DABR",
                approved_by="Dr. R. Okafor, Chief Physicist",
                vendor_doc_url="https://service.varian.example.com/cases/884213",
                status=ReturnToServiceReport.Status.RETURNED,
            )
            self.stdout.write(self.style.SUCCESS("Created a sample report."))
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
