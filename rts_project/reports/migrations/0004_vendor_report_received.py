# Replace the vendor documentation link with a "vendor report received" checkbox.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0003_outage_issue_partial_reports"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="returntoservicereport",
            name="vendor_doc_url",
        ),
        migrations.AddField(
            model_name="returntoservicereport",
            name="vendor_report_received",
            field=models.BooleanField(
                default=False,
                help_text="Tick once the vendor's service report / documentation has been received.",
                verbose_name="Vendor report received",
            ),
        ),
    ]
