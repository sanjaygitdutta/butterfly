# Fractal 6-Leg Dual Butterfly (`PE-CE BTFLY`) Real-Time Pricing Engine

A high-performance algorithmic options pricing engine and real-time dashboard replicating the **Fractal Client NSE-FNO** and institutional **Excel Spread Pricing Matrix**.

Supports **Live Upstox API v2/v3 WebSocket feeds** (with Protobuf market depth decoding) and a built-in realistic **NIFTY Options Simulator**.

---

## 1. How the Prices Are Calculated

### A. Strike Generation Geometry
For each combo configuration defined by **Gap** ($G$) and **Wing / BTFLY** ($W$), given a row **Center Strike** ($C$):

* **Put Butterfly (PE Fly)** center: $K_{PE,\text{mid}} = C - \frac{G}{2}$
  * **Leg 1**: `PE` at $C - \frac{G}{2} - W$ &rarr; **BUY 1**
  * **Leg 2**: `PE` at $C - \frac{G}{2}$ &rarr; **SELL 2**
  * **Leg 3**: `PE` at $C - \frac{G}{2} + W$ &rarr; **BUY 1** *(Designated Bidding Leg)*

* **Call Butterfly (CE Fly)** center: $K_{CE,\text{mid}} = C + \frac{G}{2}$
  * **Leg 4**: `CE` at $C + \frac{G}{2} - W$ &rarr; **BUY 1**
  * **Leg 5**: `CE` at $C + \frac{G}{2}$ &rarr; **SELL 2**
  * **Leg 6**: `CE` at $C + \frac{G}{2} + W$ &rarr; **BUY 1**

---

### B. BCmp (Buy Comparison / Debit) Formula
To **BUY** the composite strategy:
$$\text{Debit Cost} = \text{Ask}(PE_1) - 2 \cdot \text{Bid}(PE_2) + \text{Ask}(PE_3) + \text{Ask}(CE_4) - 2 \cdot \text{Bid}(CE_5) + \text{Ask}(CE_6)$$

In terminal/Excel convention, cash outflow (debit) is negative:
$$\mathbf{BCmp} = - (\text{Debit Cost})$$

### C. SCmp (Sell Comparison / Credit) Formula
To **SELL** the composite strategy:
$$\text{Credit Received} = \text{Bid}(PE_1) - 2 \cdot \text{Ask}(PE_2) + \text{Bid}(PE_3) + \text{Bid}(CE_4) - 2 \cdot \text{Ask}(CE_5) + \text{Bid}(CE_6)$$

Cash inflow (credit) is positive:
$$\mathbf{SCmp} = + (\text{Credit Received})$$

---

## 2. Quick Start

### A. Run in Terminal (CLI Mode)
Runs an interactive, live-updating Rich terminal matrix:
```bash
# Using realistic simulated NIFTY feed (works anytime, even off-market)
python run_cli.py --mode sim

# Using live Upstox API feed
python run_cli.py --mode upstox
```

### B. Run Web Dashboard
Launches a browser dashboard on `http://localhost:8000`:
```bash
python run_web.py
```
* **Real-time WebSocket streaming** updates matrix prices every 500ms.
* **Click any combo cell** (e.g., `500/200` at `23050`) to open the **"Add Strategy" modal**, matching Screenshot 1 with the 6 legs, live quotes, and exact mathematical breakdown.

---

## 3. Configuring Upstox API

To stream live market ticks from Upstox:
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Enter your Upstox credentials:
   ```env
   UPSTOX_API_KEY=your_api_key
   UPSTOX_API_SECRET=your_api_secret
   UPSTOX_ACCESS_TOKEN=your_access_token
   ```
3. Run with `--mode upstox`. The engine will download the NSE contract master, map all required strikes, and subscribe to full depth order books over WebSockets.

---

## 4. Project Structure
```
butterfly/
├── config.py                 # Engine and Upstox configurations
├── engine/
│   ├── combo.py              # 6-Leg strike math & BCmp/SCmp formulas
│   └── matrix.py             # Real-time multi-combo grid manager
├── feed/
│   ├── base.py               # Abstract feed interface
│   ├── simulator.py          # Realistic Black-Scholes NIFTY options feed
│   └── upstox_feed.py        # Upstox v2/v3 Protobuf WebSocket feed
├── display/
│   └── terminal_table.py     # Rich terminal matrix renderer
├── web/
│   ├── app.py                # FastAPI & WebSocket backend
│   └── static/
│       ├── index.html        # Web dashboard & Add Strategy modal
│       ├── style.css         # Trading terminal styling
│       └── app.js            # WebSocket client & formula explorer
├── test_engine.py            # Math verification test suite
├── run_cli.py                # CLI launcher
└── run_web.py                # Web server launcher
```
