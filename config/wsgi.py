import os
from django.core.wsgi import get_wsgi_application

# Ensure Django uses the correct settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()