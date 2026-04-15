import os
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

# Ensure Django uses the correct settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _ensure_render_sqlite_migrated():
    """Auto-bootstrap fallback sqlite on Render to avoid login/runtime 500."""
    if (os.getenv("RENDER") or "").lower() != "true":
        return
    db = settings.DATABASES.get("default", {})
    if db.get("ENGINE") != "django.db.backends.sqlite3":
        return
    db_path = Path(str(db.get("NAME") or "")).expanduser()
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    needs_migrate = not db_path.exists()
    if not needs_migrate:
        try:
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='django_migrations'"
                ).fetchone()
                needs_migrate = row is None
        except sqlite3.Error:
            needs_migrate = True

    if needs_migrate:
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)


_ensure_render_sqlite_migrated()
application = get_wsgi_application()