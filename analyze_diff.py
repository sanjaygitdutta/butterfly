"""
Analysis script to reverse-engineer the exact '1-2' column formula in Excel.
We have the exact live quotes from Upstox at ~12:36 - 12:50.
Let's test candidate formulas:
Excel values for 'NIFTY - Str' and '1-2':
22850: 319.85, -152.8
22900: 283.45, -164.25
22950: 251.80, -178.65
23000: 227.00, -188.70
23050: 209.15, -194.20
23100: 200.75, -193.75
23150: 200.25, -192.30
23200: 209.85, -183.30
23250: 227.95, -170.85
23300: 253.85, -154.00
23350: 285.85, -136.50
23400: 322.30, -117.55
23450: 364.35, -98.00
23500: 408.20, -80.80
"""
import os
from dotenv import load_dotenv
import upstox_client

load_dotenv()
c = upstox_client.Configuration()
c.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
api_client = upstox_client.ApiClient(c)
options_api = upstox_client.OptionsApi(api_client)
quote_api = upstox_client.MarketQuoteApi(api_client)

contracts = options_api.get_option_contracts("NSE_INDEX|Nifty 50").data
expiries = sorted(list({str(c.expiry)[:10] for c in contracts}))
curr_exp = expiries[0]

inst_keys = {}
for c in contracts:
    if str(c.expiry)[:10] == curr_exp:
        inst_keys[(float(c.strike_price), c.instrument_type)] = c.instrument_key

# Let's fetch full quotes for a few strikes
test_strikes = [22850, 23050, 23150, 23300, 23500]
symbols = []
for s in test_strikes:
    if (s, "CE") in inst_keys: symbols.append(inst_keys[(s, "CE")])
    if (s, "PE") in inst_keys: symbols.append(inst_keys[(s, "PE")])

quotes = quote_api.get_full_market_quote(",".join(symbols[:50]), api_version="2.0").data

def get_quote(strike, opt_type):
    k = inst_keys.get((strike, opt_type))
    if not k or k not in quotes: return None
    q = quotes[k]
    # depth
    best_bid = q.depth.buy[0].price if q.depth and q.depth.buy else q.last_price
    best_ask = q.depth.sell[0].price if q.depth and q.depth.sell else q.last_price
    return {"bid": best_bid, "ask": best_ask, "ltp": q.last_price}

print("Live Quotes Sample:")
for s in test_strikes:
    ce = get_quote(s, "CE")
    pe = get_quote(s, "PE")
    if ce and pe:
        straddle_ask = ce["ask"] + pe["ask"]
        straddle_bid = ce["bid"] + pe["bid"]
        print(f"Strike {s}: CE({ce['bid']}/{ce['ask']}), PE({pe['bid']}/{pe['ask']}) -> Straddle: {straddle_ask:.2f} / {straddle_bid:.2f}")

