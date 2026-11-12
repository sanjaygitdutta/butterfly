import sys
import os

# Add project root to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from web.app import app
except Exception as e:
    import traceback
    err_msg = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    
    app = FastAPI(title="Error")
    
    @app.get("/{full_path:path}")
    def catch_all(full_path: str = ""):
        return HTMLResponse(
            f"<html><body style='background:#0f172a;color:#f8fafc;font-family:monospace;padding:24px;'>"
            f"<h2 style='color:#f43f5e;'>FastAPI Startup Error on Vercel</h2>"
            f"<pre style='background:#1e293b;padding:16px;border-radius:8px;overflow-x:auto;color:#cbd5e1;'>{err_msg}</pre>"
            f"</body></html>",
            status_code=500
        )
