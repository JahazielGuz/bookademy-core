"""Drop `kind` now that a topic is the unit again.

Separate from the merge because Postgres will not ALTER a table in the same
transaction as data changes with pending constraint triggers.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0007_topic_is_the_unit_again")]

    operations = [migrations.RemoveField(model_name="topic", name="kind")]
