from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('department_stock', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stock',
            name='quantity',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='transferrequest',
            name='requested_quantity',
            field=models.PositiveIntegerField(default=1),
        ),
    ]
