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

@app.get("/", response_class=HTMLResponse)
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
        return {"error": "UPSTOX_API_KEY is not set in .env yet. Please save your API Key first."}
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")
    login_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={urllib.parse.quote(redirect_uri)}"
    return RedirectResponse(url=login_url)

@app.get("/callback")
def oauth_callback(code: str):
    import urllib.request
    import urllib.parse
    import json
    from fastapi.responses import HTMLResponse
    
    api_key = os.getenv("UPSTOX_API_KEY", upstox_config.api_key)
    api_secret = os.getenv("UPSTOX_API_SECRET", upstox_config.api_secret)
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")
    
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
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(token_url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            access_token = body.get("access_token", "")
            
        if access_token:
            # Update .env
            env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            with open(env_file, "w") as f:
                f.write("# Upstox API v2 Credentials\n")
                f.write(f"UPSTOX_API_KEY={api_key}\n")
                f.write(f"UPSTOX_API_SECRET={api_secret}\n")
                f.write(f"UPSTOX_REDIRECT_URI={redirect_uri}\n")
                f.write(f"UPSTOX_ACCESS_TOKEN={access_token}\n")
                
            os.environ["UPSTOX_ACCESS_TOKEN"] = access_token
            upstox_config.access_token = access_token
            init_feed(prefer_upstox=True, custom_token=access_token)
                
            return HTMLResponse("""
            <html>
            <body style="font-family: sans-serif; background: #0a0e17; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh;">
                <div style="background: #121826; padding: 40px; border-radius: 12px; border: 1px solid #10b981; text-align: center;">
                    <h2 style="color: #10b981; margin-bottom: 12px;">Upstox Connected Successfully!</h2>
                    <p style="color: #94a3b8; margin-bottom: 20px;">Live access token generated and activated. Dashboard is now streaming real-time market data!</p>
                    <a href="/" style="background: #3b82f6; color: #fff; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 600;">Return to Dashboard</a>
                </div>
            </body>
            </html>
            """)
        else:
            return {"error": "Failed to extract access_token", "response": body}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/switch-feed")
def switch_feed(mode: str = "sim"):
    if mode == "upstox":
        init_feed(prefer_upstox=True)
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
def get_matrix_state():
    spot = getattr(feed, "spot", 25255.0)
    if spot > 0:
        matrix.set_spot(spot)
    if feed_mode and "Simulator" in feed_mode and hasattr(feed, "generate_all_quotes"):
        quotes = feed.generate_all_quotes()
        on_batch(quotes)
    all_combos = [c[2] for c in matrix.combos_current] + [c[2] for c in matrix.combos_next]
    return {
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

# Pre-initialize on module load for serverless environments
init_feed(prefer_upstox=bool(os.getenv("UPSTOX_ACCESS_TOKEN", upstox_config.access_token)))

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
