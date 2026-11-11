import sys
import os

# Add project root to sys.path so modules like engine, feed, web can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app

# Vercel looks for 'app' or handler in api/index.py

