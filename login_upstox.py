"""
One-click Upstox OAuth Login & Access Token Generator.
Starts a temporary local server to capture the authorization code, exchanges it
for an access token, and automatically saves it to your .env file.
"""
import os
import sys
import webbrowser
import urllib.parse
import urllib.request
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

REDIRECT_PORT = 8000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            query_params = urllib.parse.parse_qs(parsed.query)
            if "code" in query_params:
                OAuthCallbackHandler.auth_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = """
                <html>
                <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh;">
                    <div style="background: #1e293b; padding: 30px; border-radius: 12px; text-align: center; border: 1px solid #334155;">
                        <h2 style="color: #10b981;">Upstox Login Successful!</h2>
                        <p>Authorization code received. You can close this tab and return to your terminal.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_response(400)
                self.wfile.write(b"Error: Code parameter missing.")

    def log_message(self, format, *args):
        return  # Suppress normal HTTP logging

def exchange_code_for_token(api_key: str, api_secret: str, code: str) -> str:
    token_url = "https://api.upstox.com/v2/login/authorization/token"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": api_key,
        "client_secret": api_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    req = urllib.request.Request(token_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("access_token", "")
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        print(f"\n[Token Exchange Error]: {error_msg}")
        return ""

def main():
    print("==================================================")
    print("       UPSTOX ONE-CLICK LOGIN & TOKEN SETUP       ")
    print("==================================================")

    # 1. Ask for API Key and API Secret if not already in .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    existing_key = ""
    existing_secret = ""

    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("UPSTOX_API_KEY="):
                    existing_key = line.split("=", 1)[1].strip()
                elif line.startswith("UPSTOX_API_SECRET="):
                    existing_secret = line.split("=", 1)[1].strip()

    api_key = input(f"Enter your Upstox API Key [{existing_key}]: ").strip() or existing_key
    api_secret = input(f"Enter your Upstox API Secret [{existing_secret}]: ").strip() or existing_secret

    if not api_key or not api_secret:
        print("\n[Error] Both API Key and API Secret are required to continue.")
        sys.exit(1)

    # 2. Build Upstox Login Dialog URL
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog?"
        f"response_type=code&client_id={api_key}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    )

    print("\nStarting local listener on http://localhost:8000/callback ...")
    server = HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)

    print(f"\nOpening browser for Upstox login...\nURL: {login_url}\n")
    webbrowser.open(login_url)

    print("Waiting for you to log in on Upstox...")
    while OAuthCallbackHandler.auth_code is None:
        server.handle_request()

    code = OAuthCallbackHandler.auth_code
    print(f"\nReceived authorization code: {code[:8]}...")
    print("Exchanging code for Access Token...")

    token = exchange_code_for_token(api_key, api_secret, code)

    if not token:
        print("[Error] Failed to obtain access token. Please verify your API Key and Secret.")
        sys.exit(1)

    # 3. Write directly to .env
    with open(env_path, "w") as f:
        f.write("# Upstox API v2 Credentials\n")
        f.write(f"UPSTOX_API_KEY={api_key}\n")
        f.write(f"UPSTOX_API_SECRET={api_secret}\n")
        f.write(f"UPSTOX_REDIRECT_URI={REDIRECT_URI}\n")
        f.write(f"UPSTOX_ACCESS_TOKEN={token}\n")

    print("\nSUCCESS! Access Token retrieved and saved to .env")
    print(f"Token: {token[:12]}...{token[-8:]}")
    print("\nYou are all set! You can now run:")
    print("  python run_cli.py --mode upstox")
    print("  python run_web.py")

if __name__ == "__main__":
    main()
