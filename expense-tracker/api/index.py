"""
Vercel entrypoint.

Vercel discovers Serverless Functions inside the `api/` directory, so this
module simply re-exports the Flask app defined in app.py at the project root.
The parent directory has to be put on sys.path first, otherwise `import app`
fails once Vercel runs this file as the function entrypoint.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app  # noqa: E402

#Vercel's Python runtime looks for a WSGI callable named `app` or `handler`
handler = app
