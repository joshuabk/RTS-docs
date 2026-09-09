# Allow reports to be submitted before work is complete:
# - add the required "outage issue" field
# - make outage start required (backfilled from work completed for old rows)
# - make work completed / work performed optional
from django.db import migrations, models
from django.db.models import F


def backfill_outage_start(apps, schema_editor):
    Report = apps.get_model("reports", "ReturnToServiceReport")
    Report.objects.filter(outage_start__isnull=True).update(
        outage_start=F("work_completed_at")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0002_alter_returntoservicereport_vendor_doc_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="returntoservicereport",
            name="outage_issue",
            field=models.TextField(
                default="",
                help_text="What went wrong - the fault or reason the machine was taken out of service.",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_outage_start, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="returntoservicereport",
            name="outage_start",
            field=models.DateTimeField(help_text="When the machine went out of service."),
        ),
        migrations.AlterField(
            model_name="returntoservicereport",
            name="work_completed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When repair / maintenance work was completed. Leave blank while work is ongoing.",
            ),
        ),
        migrations.AlterField(
            model_name="returntoservicereport",
            name="work_performed",
            field=models.TextField(
                blank=True,
                help_text="Description of the repair / maintenance performed.",
            ),
        ),
        migrations.AlterModelOptions(
            name="returntoservicereport",
            options={
                "ordering": ["-outage_start", "-created_at"],
                "verbose_name": "return-to-service report",
            },
        ),
    ]
