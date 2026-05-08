# Generated migration for Assignment 7 - All new models and fields

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('globals', '0001_initial'),
        ('ps1', '0001_initial'),  # Adjust to your last migration
    ]

    operations = [
        # T-01: Add status and cancellation fields to IndentFile
        migrations.AddField(
            model_name='indentfile',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE', 'Active'),
                    ('CANCELLED', 'Cancelled'),
                    ('COMPLETED', 'Completed'),
                    ('REJECTED', 'Rejected')
                ],
                default='ACTIVE',
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='cancellation_reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='cancelled_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cancelled_indents',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='cancelled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        
        # T-02: Add rejection fields to IndentFile
        migrations.AddField(
            model_name='indentfile',
            name='rejection_reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='rejected_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rejected_indents',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='rejected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        
        # T-14: Add SLA fields to IndentFile
        migrations.AddField(
            model_name='indentfile',
            name='sla_deadline',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='escalated',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='indentfile',
            name='escalation_count',
            field=models.IntegerField(default=0),
        ),
        
        # T-07: Validators are enforced at model level (IndentItem not in 0001)

        
        # T-09: Create Vendor model
        migrations.CreateModel(
            name='Vendor',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_code', models.CharField(max_length=50, unique=True)),
                ('vendor_name', models.CharField(max_length=250)),
                ('contact_person', models.CharField(blank=True, max_length=250)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('address', models.TextField(blank=True)),
                ('is_approved', models.BooleanField(default=False)),
                ('gst_number', models.CharField(blank=True, max_length=15)),
                ('pan_number', models.CharField(blank=True, max_length=10)),
                ('rating', models.DecimalField(decimal_places=2, default=0.0, max_digits=3)),
                ('total_orders', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'Vendor',
                'ordering': ['vendor_name'],
            },
        ),
        
        # T-09, T-16: Modify StockEntry - vendor as ForeignKey and asset fields
        migrations.RemoveField(
            model_name='stockentry',
            name='vendor',
        ),
        migrations.AddField(
            model_name='stockentry',
            name='vendor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='stock_entries',
                to='ps1.vendor',
                default=1  # Set a default vendor_id, remove after data migration
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='stockentry',
            name='is_capital_asset',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='stockentry',
            name='capitalization_threshold',
            field=models.DecimalField(decimal_places=2, default=50000.0, max_digits=12),
        ),
        
        # T-16: Add asset_tag to StockItem
        migrations.AddField(
            model_name='stockitem',
            name='asset_tag',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        
        # T-13: Create StockReservation model
        migrations.CreateModel(
            name='StockReservation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('reserved_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('indent_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='ps1.indentfile')),
                ('reserved_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('stock_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reservations', to='ps1.stockitem')),
            ],
            options={
                'db_table': 'StockReservation',
                'ordering': ['-reserved_at'],
            },
        ),
        
        # T-04: Create GoodsReceivedNote model
        migrations.CreateModel(
            name='GoodsReceivedNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grn_number', models.CharField(max_length=100, unique=True)),
                ('received_date', models.DateTimeField(auto_now_add=True)),
                ('confirmed_date', models.DateTimeField(blank=True, null=True)),
                ('quantity_received', models.IntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('quantity_accepted', models.IntegerField(validators=[django.core.validators.MinValueValidator(0)])),
                ('quality_check_passed', models.BooleanField(default=True)),
                ('remarks', models.TextField(blank=True)),
                ('has_discrepancy', models.BooleanField(default=False)),
                ('discrepancy_details', models.TextField(blank=True)),
                ('invoice_release_approved', models.BooleanField(default=False)),
                ('confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='confirmed_grns', to=settings.AUTH_USER_MODEL)),
                ('indent_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grns', to='ps1.indentfile')),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='received_grns', to=settings.AUTH_USER_MODEL)),
                ('stock_entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grns', to='ps1.stockentry')),
            ],
            options={
                'db_table': 'GoodsReceivedNote',
                'ordering': ['-received_date'],
            },
        ),
        
        # T-05: Create ProductReturn model
        migrations.CreateModel(
            name='ProductReturn',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('return_number', models.CharField(max_length=100, unique=True)),
                ('return_reason', models.TextField()),
                ('quantity_returned', models.IntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('return_date', models.DateTimeField(auto_now_add=True)),
                ('has_discrepancy', models.BooleanField(default=True)),
                ('discrepancy_type', models.CharField(blank=True, max_length=100)),
                ('discrepancy_description', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Review'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                        ('REFUNDED', 'Refunded'),
                        ('REPLACED', 'Replaced')
                    ],
                    default='PENDING',
                    max_length=20
                )),
                ('resolution_type', models.CharField(
                    blank=True,
                    choices=[('REFUND', 'Refund'), ('REPLACE', 'Replace'), ('REJECT', 'Reject Claim')],
                    max_length=20
                )),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('resolution_remarks', models.TextField(blank=True)),
                ('invoice_hold', models.BooleanField(default=True)),
                ('invoice_hold_released', models.BooleanField(default=False)),
                ('grn', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='returns', to='ps1.goodsreceivednote')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_returns', to=settings.AUTH_USER_MODEL)),
                ('return_initiated_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='initiated_returns', to=settings.AUTH_USER_MODEL)),
                ('stock_entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='returns', to='ps1.stockentry')),
            ],
            options={
                'db_table': 'ProductReturn',
                'ordering': ['-return_date'],
            },
        ),
        
        # T-08: Create Tender model
        migrations.CreateModel(
            name='Tender',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tender_number', models.CharField(max_length=100, unique=True)),
                ('title', models.CharField(max_length=250)),
                ('description', models.TextField()),
                ('estimated_value', models.DecimalField(decimal_places=2, max_digits=12)),
                ('publish_date', models.DateTimeField(blank=True, null=True)),
                ('bid_submission_deadline', models.DateTimeField()),
                ('bid_opening_date', models.DateTimeField()),
                ('status', models.CharField(
                    choices=[
                        ('DRAFT', 'Draft'),
                        ('PUBLISHED', 'Published'),
                        ('BIDDING', 'Bidding Open'),
                        ('EVALUATION', 'Under Evaluation'),
                        ('AWARDED', 'Awarded'),
                        ('CANCELLED', 'Cancelled')
                    ],
                    default='DRAFT',
                    max_length=20
                )),
                ('awarded_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('awarded_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('awarded_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='awarded_tenders', to='ps1.vendor')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('indent_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tenders', to='ps1.indentfile')),
            ],
            options={
                'db_table': 'Tender',
                'ordering': ['-created_at'],
            },
        ),
        
        # T-08: Create TenderBid model
        migrations.CreateModel(
            name='TenderBid',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bid_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('bid_document', models.FileField(blank=True, upload_to='tender_bids/')),
                ('technical_compliance', models.BooleanField(default=False)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('evaluated', models.BooleanField(default=False)),
                ('evaluation_score', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('evaluation_remarks', models.TextField(blank=True)),
                ('is_winner', models.BooleanField(default=False)),
                ('tender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bids', to='ps1.tender')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bids', to='ps1.vendor')),
            ],
            options={
                'db_table': 'TenderBid',
                'ordering': ['bid_amount'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='tenderbid',
            unique_together={('tender', 'vendor')},
        ),
        
        # T-23: Create AuditLog model
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('action', models.CharField(max_length=100)),
                ('entity_type', models.CharField(max_length=50)),
                ('entity_id', models.IntegerField()),
                ('old_value', models.TextField(blank=True)),
                ('new_value', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'AuditLog',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['timestamp'], name='AuditLog_timesta_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['user', 'timestamp'], name='AuditLog_user_ti_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['entity_type', 'entity_id'], name='AuditLog_entity__idx'),
        ),
    ]
