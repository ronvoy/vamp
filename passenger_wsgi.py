import os
import sys

# Add the app directory to the Python path so imports resolve correctly
app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
sys.path.insert(0, app_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(app_dir, ".env"))

from app import application as _app

ROOT_URL = os.environ.get("ROOT_URL", "").rstrip("/")

if ROOT_URL:
    class _PrefixMiddleware:
        def __init__(self, app, prefix):
            self.app = app
            self.prefix = prefix

        def __call__(self, environ, start_response):
            path = environ.get("PATH_INFO", "")
            if path.startswith(self.prefix):
                environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            environ["SCRIPT_NAME"] = self.prefix
            return self.app(environ, start_response)

    application = _PrefixMiddleware(_app, ROOT_URL)
else:
    application = _app
