"""
FastAPI Web Server for Real-Time Butterfly Pricing Engine Dashboard.
"""
import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from engine.matrix import PricingMatrix
from feed.simulator import SimulatorFeed
from feed.upstox_feed import UpstoxMarketFeed
from config import upstox_config, engine_config

app = FastAPI(title="6L butterfly")

possible_static_dirs = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"),
    os.path.join(os.getcwd(), "web", "static"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static"),
    "/var/task/web/static"
]
STATIC_DIR = possible_static_dirs[0]
for d in possible_static_dirs:
    if os.path.exists(os.path.join(d, "index.html")):
        STATIC_DIR = d
        break

matrix = PricingMatrix(initial_spot=25255.0)
req = matrix.get_required_strikes()
required_strikes = req["current"].union(req["next"])

feed = None
feed_mode = "Simulator"
auth_error = None

def on_batch(quotes):
    spot = getattr(feed, "spot", 0.0)
    if spot > 0:
        matrix.set_spot(spot)
    matrix.update_quotes_batch(quotes)
    matrix.recompute_all()

def init_feed(prefer_upstox=True, custom_token=None):
    global feed, feed_mode, auth_error
    if feed:
        try:
            feed.stop()
        except Exception:
            pass

    current_spot = matrix.spot if matrix.spot > 20000 else 25255.0
    req = matrix.get_required_strikes()
    req_strikes = req["current"].union(req["next"])

    is_vercel = bool(os.getenv("VERCEL"))
    token = custom_token or os.getenv("UPSTOX_ACCESS_TOKEN", upstox_config.access_token)
    if prefer_upstox and token and not is_vercel:
        try:
            import upstox_client
            cfg = upstox_client.Configuration()
            cfg.access_token = token
            user_api = upstox_client.UserApi(upstox_client.ApiClient(cfg))
            profile = user_api.get_profile("2.0")
            user_name = profile.data.user_name if profile and profile.data else "Live"
            
            feed = UpstoxMarketFeed(access_token=token, required_strikes=req_strikes, matrix=matrix)
            feed_mode = f"Upstox Live ({user_name})"
            auth_error = None
            print(f"[Feed] Upstox Live authenticated successfully as: {user_name}")
        except Exception as e:
            print(f"[Feed] Upstox token error: {e}. Falling back to Realistic Simulator.")
            auth_error = "Upstox Access Token Expired (401 Unauthorized). Switched to Simulator Feed. Click 'Login to Upstox' to generate today's live token."
            feed = SimulatorFeed(required_strikes=req_strikes, initial_spot=current_spot, tick_interval=0.5)
            feed_mode = "Simulator (Upstox Token Expired)"
    else:
        feed = SimulatorFeed(required_strikes=req_strikes, initial_spot=current_spot, tick_interval=0.5)
        feed_mode = "Simulator"
        auth_error = None

    feed.on_batch(on_batch)
    if hasattr(feed, "generate_all_quotes"):
        try:
            initial_quotes = feed.generate_all_quotes()
            on_batch(initial_quotes)
        except Exception:
            pass

    # Serverless (Vercel) cannot run background loop threads
    if not is_vercel:
        try:
            feed.start()
        except Exception as e:
            print(f"[Feed] feed.start() error: {e}")

# Active WebSocket connections
active_connections: List[WebSocket] = []

@app.on_event("startup")
def startup_event():
    init_feed(prefer_upstox=True)

@app.on_event("shutdown")
def shutdown_event():
    if feed:
        feed.stop()

def _find_file(filename: str) -> Optional[str]:
    p = os.path.join(STATIC_DIR, filename)
    if os.path.exists(p):
        return p
    for root, dirs, files in os.walk(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        if filename in files:
            return os.path.join(root, filename)
    return None

@app.get("/favicon.ico")
def get_favicon():
    return Response(content=b"", media_type="image/x-icon", status_code=200)

@app.get("/", response_class=HTMLResponse)
@app.get("/api/index", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
def get_index():
    path = _find_file("index.html")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>6L butterfly Dashboard</h1><p>Index template loading...</p>", status_code=200)

@app.get("/static/app.js")
@app.get("/app.js")
def get_app_js():
    path = _find_file("app.js")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/javascript")
    return Response(content="// app.js", status_code=200)

@app.get("/static/style.css")
@app.get("/style.css")
def get_style_css():
    path = _find_file("style.css")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/css")
    return Response(content="/* style.css */", status_code=200)

try:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
except Exception:
    pass

@app.get("/login")
def login_redirect():
    import urllib.parse
    from fastapi.responses import RedirectResponse
    api_key = os.getenv("UPSTOX_API_KEY", upstox_config.api_key)
    if not api_key:
        return HTMLResponse("<h2 style='color:red'>UPSTOX_API_KEY not set in environment. Add it to Vercel Environment Variables.</h2>")
    is_vercel = bool(os.getenv("VERCEL"))
    if is_vercel:
        # On Vercel, redirect_uri must point to the deployed domain
        redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "https://butterfly-sooty.vercel.app/callback")
    else:
        redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")
    params = {
        "response_type": "code",
        "client_id": api_key,
        "redirect_uri": redirect_uri
    }
    login_url = f"https://api.upstox.com/v2/login/authorization/dialog?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=login_url)

@app.get("/callback")
def oauth_callback(code: str):
    import urllib.request
    import urllib.parse
    import json

    api_key = os.getenv("UPSTOX_API_KEY", upstox_config.api_key)
    api_secret = os.getenv("UPSTOX_API_SECRET", upstox_config.api_secret)
    is_vercel = bool(os.getenv("VERCEL"))
    if is_vercel:
        redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "https://butterfly-sooty.vercel.app/callback")
    else:
        redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    token_url = "https://api.upstox.com/v2/login/authorization/token"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0"
    }
    post_data = urllib.parse.urlencode({
        "code": code,
        "client_id": api_key,
        "client_secret": api_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    try:
        req_obj = urllib.request.Request(token_url, data=post_data, headers=headers, method="POST")
        with urllib.request.urlopen(req_obj) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            access_token = body.get("access_token", "")

        if not access_token:
            return HTMLResponse(f"<h2 style='color:red'>Token exchange failed: {body}</h2>")

        # --- On localhost: save to .env + init live feed immediately ---
        if not is_vercel:
            env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            try:
                with open(env_file, "w") as f:
                    f.write("# Upstox API v2 Credentials\n")
                    f.write(f"UPSTOX_API_KEY={api_key}\n")
                    f.write(f"UPSTOX_API_SECRET={api_secret}\n")
                    f.write(f"UPSTOX_REDIRECT_URI={redirect_uri}\n")
                    f.write(f"UPSTOX_ACCESS_TOKEN={access_token}\n")
            except Exception:
                pass
            os.environ["UPSTOX_ACCESS_TOKEN"] = access_token
            upstox_config.access_token = access_token
            init_feed(prefer_upstox=True, custom_token=access_token)

        # --- On BOTH localhost + Vercel: save token to browser localStorage ---
        # The JS snippet stores the token and redirects to dashboard.
        # On Vercel, every future poll will carry the token as ?token=... param.
        return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>6L butterfly - Upstox Connected</title></head>
<body style="font-family: sans-serif; background: #0a0e17; color: #fff;
             display: flex; align-items: center; justify-content: center; height: 100vh; margin:0;">
  <div style="background: #121826; padding: 40px; border-radius: 12px;
              border: 1px solid #10b981; text-align: center; max-width: 420px;">
    <h2 style="color: #10b981; margin-bottom: 12px;">Upstox Connected!</h2>
    <p style="color: #94a3b8; margin-bottom: 8px;">
      Live access token generated. Saving and redirecting to dashboard...
    </p>
    <p id="status" style="color: #38bdf8; font-size: 0.85rem;">Activating live feed...</p>
  </div>
  <script>
    // Save token in browser localStorage so every poll can carry it
    // Works on both localhost and Vercel (stateless serverless)
    try {{
      localStorage.setItem('upstox_access_token', '{access_token}');
      localStorage.setItem('butterfly_feed_mode', 'live');
      document.getElementById('status').textContent = 'Token saved. Redirecting...';
    }} catch(e) {{
      document.getElementById('status').textContent = 'Could not save to localStorage: ' + e;
    }}
    setTimeout(() => {{ window.location.href = '/'; }}, 1500);
  </script>
</body>
</html>
""")

    except Exception as e:
        return HTMLResponse(f"<h2 style='color:red'>OAuth error: {e}</h2>")

@app.post("/api/switch-feed")
def switch_feed(mode: str = "sim", token: Optional[str] = None):
    """
    Switch feed mode. On localhost: persists to memory + .env.
    On Vercel: stateless — client passes token on each request via ?token=.
    """
    if mode == "upstox":
        init_feed(prefer_upstox=True, custom_token=token or None)
    else:
        init_feed(prefer_upstox=False)
    return {"feed_mode": feed_mode, "auth_error": auth_error}


@app.get("/api/strategy-details")
def get_strategy_details(center: float, gap: int, wing: int, expiry: str = "current"):
    """
    Returns exact 6 legs and price computation for the 'Add Strategy' modal.
    """
    is_nxt = (expiry in ("next", "nxt"))
    exp_tag = "nxt" if is_nxt else "current"
    results_dict = matrix.results_next if is_nxt else matrix.results_current
    combos_list = matrix.combos_next if is_nxt else matrix.combos_current

    res = None
    for (g, w, lbl) in combos_list:
        if g == gap and w == wing:
            res = results_dict.get(lbl, {}).get(center)
            break

    if not res:
        from engine.combo import generate_6leg_butterfly
        res = generate_6leg_butterfly(center, gap, wing, matrix.quotes_map, expiry=exp_tag)

    legs_data = []
    for leg in res.legs:
        q = leg.quote
        legs_data.append({
            "leg_number": leg.leg_number,
            "instrument": "OPTIDX",
            "symbol": "NIFTY",
            "expiry": "19-OCT-2026",
            "lot_size": 65,
            "option_type": leg.option_type,
            "strike": leg.strike,
            "action": leg.action,
            "ratio": leg.ratio,
            "is_bidding": leg.is_bidding,
            "bid": q.bid if q else 0.0,
            "ask": q.ask if q else 0.0,
            "ltp": q.ltp if q else 0.0
        })

    return {
        "center": center,
        "gap": gap,
        "wing": wing,
        "bcmp": res.bcmp,
        "scmp": res.scmp,
        "spread": res.spread,
        "legs": legs_data
    }

@app.get("/api/churn-stats")
def get_churn_stats(combo: str = "500/200"):
    stats = matrix.churn_tracker.get_all_active_churns(matrix.centers, combo_label=combo)
    return {
        "combo": combo,
        "atm_strike": matrix.atm,
        "strikes": stats
    }

@app.get("/api/strike-swings")
def get_strike_swings(strike: float, combo: str = "500/200"):
    key = (combo, strike)
    stats = matrix.churn_tracker.stats.get(key)
    if stats:
        return stats.to_dict()
    return {"strike": strike, "combo": combo, "churn_count": 0, "recent_swings": []}

@app.get("/api/matrix-state")
def get_matrix_state(mode: Optional[str] = None, token: Optional[str] = None):
    """
    Returns the current matrix state.

    Query params (all optional):
      ?mode=sim      → force simulator (client-side pref stored in localStorage)
      ?mode=live     → force Upstox live (requires ?token=)
      ?token=TOKEN   → Upstox access token from browser localStorage
                       (Vercel is stateless — browser carries the token each request)
    """
    is_vercel = bool(os.getenv("VERCEL"))

    # ── Determine effective feed for this request ──────────────────────────
    effective_feed = feed
    effective_feed_mode = feed_mode
    effective_auth_error = auth_error

    if is_vercel:
        # On Vercel every Lambda is fresh — use the token/mode the browser sends
        if token and mode != "sim":
            # Browser has a valid Upstox token → try live fetch
            try:
                import upstox_client
                cfg = upstox_client.Configuration()
                cfg.access_token = token
                # Quick profile check to validate token
                user_api = upstox_client.UserApi(upstox_client.ApiClient(cfg))
                profile = user_api.get_profile("2.0")
                user_name = profile.data.user_name if profile and profile.data else "Live"

                req_s = matrix.get_required_strikes()
                req_strikes = req_s["current"].union(req_s["next"])
                effective_feed = UpstoxMarketFeed(
                    access_token=token,
                    required_strikes=req_strikes,
                    matrix=matrix
                )
                effective_feed.on_batch(on_batch)
                # Fetch real option chain prices and spot via REST snapshot (works in serverless Lambda)
                real_quotes = effective_feed.fetch_quotes_snapshot()
                if real_quotes:
                    on_batch(real_quotes)

                effective_feed_mode = f"Upstox Live ({user_name})"
                effective_auth_error = None
            except Exception as e:
                err_msg = str(e)
                effective_auth_error = f"Token invalid or expired: {err_msg[:80]}. Please login again."
                effective_feed_mode = "Simulator (Token Error)"
                # Fall through to simulator below

        if not token or mode == "sim" or "Simulator" in effective_feed_mode:
            # Simulator mode: generate fresh quotes for this request
            try:
                req_s = matrix.get_required_strikes()
                req_strikes = req_s["current"].union(req_s["next"])
                effective_feed = SimulatorFeed(
                    required_strikes=req_strikes,
                    initial_spot=matrix.spot if matrix.spot > 20000 else 25255.0,
                    tick_interval=0.5
                )
                effective_feed.on_batch(on_batch)
                if mode == "sim":
                    effective_feed_mode = "Simulator"
                    effective_auth_error = None
            except Exception as e:
                print(f"[matrix-state] sim init error: {e}")

    # ── Generate quotes ────────────────────────────────────────────────────
    spot = getattr(effective_feed, "spot", 25255.0) if effective_feed else 25255.0
    if spot > 0:
        matrix.set_spot(spot)

    if effective_feed and hasattr(effective_feed, "generate_all_quotes"):
        try:
            quotes = effective_feed.generate_all_quotes()
            on_batch(quotes)
        except Exception:
            pass

    all_combos = [c[2] for c in matrix.combos_current] + [c[2] for c in matrix.combos_next]
    return {
        "spot": spot,
        "atm_strike": matrix.atm,
        "feed_mode": effective_feed_mode,
        "auth_error": effective_auth_error,
        "current": matrix.to_table_data("current"),
        "next": matrix.to_table_data("next"),
        "combos_current": [c[2] for c in matrix.combos_current],
        "combos_next": [c[2] for c in matrix.combos_next],
        "churn_leaderboards": {c: matrix.churn_tracker.get_stats_for_combo(c)[:5] for c in all_combos},
        "churn_leaderboard": matrix.churn_tracker.get_stats_for_combo("500/200")[:5],
    }

# Pre-initialize on module load — only for serverless (Vercel) with simulator
# For local dev, startup_event() handles this via uvicorn lifecycle
_is_vercel = bool(os.getenv("VERCEL"))
if _is_vercel:
    try:
        # On Vercel: always use Simulator (no live broker feed possible)
        init_feed(prefer_upstox=False)
    except Exception as _e:
        print(f"[Vercel startup] init_feed error (non-fatal): {_e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Broadcast state every 500ms
            spot = getattr(feed, "spot", 23135.4)
            if spot > 0:
                matrix.set_spot(spot)
            all_combos = [c[2] for c in matrix.combos_current] + [c[2] for c in matrix.combos_next]
            data = {
                "spot": spot,
                "atm_strike": matrix.atm,
                "feed_mode": feed_mode,
                "auth_error": auth_error,
                "current": matrix.to_table_data("current"),
                "next": matrix.to_table_data("next"),
                "combos_current": [c[2] for c in matrix.combos_current],
                "combos_next": [c[2] for c in matrix.combos_next],
                "churn_leaderboards": {c: matrix.churn_tracker.get_stats_for_combo(c)[:5] for c in all_combos},
                "churn_leaderboard": matrix.churn_tracker.get_stats_for_combo("500/200")[:5],
            }
            await websocket.send_json(data)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)
