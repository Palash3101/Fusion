from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ps", "0005_alter_indent_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="indent",
            name="delivery_confirmed",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="indent",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("UNDER_HOD_REVIEW", "Under HOD Review"),
                    ("STOCK_CHECKED", "Stock Checked"),
                    ("INTERNAL_ISSUED", "Internal Issued"),
                    ("EXTERNAL_PROCUREMENT", "External Procurement"),
                    ("FORWARDED_TO_DIRECTOR", "Forwarded to Director"),
                    ("APPROVED_BY_DEP_ADMIN", "Approved by Dept Admin"),
                    ("APPROVED", "Approved"),
                    ("STOCKED", "Stocked"),
                    ("REJECTED", "Rejected"),
                    ("FORWARDED", "Forwarded"),
                    ("BIDDING", "Bidding"),
                    ("PURCHASED", "Purchased"),
                    ("STOCK_ENTRY", "Stock Entry"),
                ],
                default="DRAFT",
                max_length=30,
            ),
        ),
    ]
