from django.core.management import call_command
from django.db import migrations

CACHE_TABLE = "django_cache"


def create_cache_table(apps, schema_editor):
    # createcachetable skips tables that already exist, so this is safe to re-run
    call_command(
        "createcachetable",
        CACHE_TABLE,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def drop_cache_table(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS %s" % CACHE_TABLE)


class Migration(migrations.Migration):
    """
    The database cache needs its table before any cached view runs. Creating it
    here means a deploy that runs migrate cannot forget the separate
    createcachetable step and 500 on every rate-limited request.
    """

    dependencies = [
        ("core", "0025_broadcastnotification"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
