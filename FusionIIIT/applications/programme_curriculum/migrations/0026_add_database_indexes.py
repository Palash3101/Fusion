# Database Optimization Migration for Student List Generation
# NOTE: Replaced with no-op — original RunSQL referenced 'course_registration'
# table which does not exist in fresh test databases.
# Indexes can be applied manually on production if needed.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('programme_curriculum', '0025_update_minority_values'),
    ]

    operations = [
        # No-op: original indexes referenced non-existent course_registration table
    ]
