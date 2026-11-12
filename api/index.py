"""
Vercel serverless entrypoint for 6L Butterfly.
This file must have 'app' at the top level for Vercel's AST scanner.
"""
import sys
import os

# Ensure project root is on the path BEFORE any imports
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Mark as serverless so web/app.py skips background threads and live feed
os.environ.setdefault("VERCEL", "1")

from web.app import app  # noqa: E402  -- must be top-level for Vercel
