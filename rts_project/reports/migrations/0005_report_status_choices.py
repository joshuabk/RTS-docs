# Status options: pending / service complete / returned to treatment (draft removed).
from django.db import migrations, models


def draft_to_pending(apps, schema_editor):
    Report = apps.get_model("reports", "ReturnToServiceReport")
    Report.objects.filter(status="draft").update(status="pending")


def pending_to_draft(apps, schema_editor):
    Report = apps.get_model("reports", "ReturnToServiceReport")
    Report.objects.filter(status__in=["pending", "service_complete"]).update(status="draft")


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0004_vendor_report_received"),
    ]

    operations = [
        migrations.AlterField(
            model_name="returntoservicereport",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("service_complete", "Service complete"),
                    ("returned", "Returned to treatment"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(draft_to_pending, pending_to_draft),
    ]
