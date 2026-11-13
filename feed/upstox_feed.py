"""
Live Upstox API v2 / v3 Market Data WebSocket Feed.
Connects using upstox-python-sdk MarketDataStreamerV3 with Protobuf decoding.
Maps NIFTY option contracts directly via Upstox OptionsApi.
"""
import os
import threading
from typing import Dict, List, Set, Tuple, Optional, Any
try:
    import upstox_client
    from upstox_client.feeder import MarketDataStreamerV3
except Exception as _e:
    upstox_client = None
    MarketDataStreamerV3 = None
from .base import BaseMarketFeed
from engine.combo import OptionQuote
from config import upstox_config

def _extract_val(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

class UpstoxMarketFeed(BaseMarketFeed):
    def __init__(
        self,
        access_token: Optional[str] = None,
        required_strikes: Optional[Set[Tuple[float, str]]] = None,
        symbol: str = "NIFTY",
        target_expiry: Optional[str] = None,
        matrix: Optional[Any] = None
    ):
        super().__init__()
        self.access_token = access_token or upstox_config.access_token
        self.required_strikes = required_strikes or set()
        self.symbol = symbol
        self.target_expiry = target_expiry
        self.matrix = matrix
        
        # Spot price tracking (default to 25299.0)
        self.spot: float = 25299.0
        
        # Mapping: instrument_key -> (strike, option_type, expiry_tag)
        self.instrument_map: Dict[str, Tuple[float, str, str]] = {}
        # Mapping: (expiry_tag, strike, option_type) -> instrument_key
        self.strike_to_instrument: Dict[Tuple[str, float, str], str] = {}
        
        self.streamer: Optional[MarketDataStreamerV3] = None
        self._is_connected = False
        self.available_expiries: List[str] = []

    def fetch_and_map_instruments(self):
        """
        Loads NIFTY option contracts using Upstox OptionsApi.
        Automatically tags the closest expiry as 'current' and the second as 'nxt'.
        """
        print("[Upstox Feed] Fetching active NIFTY option contracts via OptionsApi...")
        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token
        api_client = upstox_client.ApiClient(configuration)

        try:
            # 1. Fetch live spot
            quote_api = upstox_client.MarketQuoteApi(api_client)
            ltp_res = quote_api.ltp(symbol="NSE_INDEX|Nifty 50", api_version="2.0")
            if ltp_res and ltp_res.data:
                data_dict = ltp_res.data if isinstance(ltp_res.data, dict) else (ltp_res.data.to_dict() if hasattr(ltp_res.data, "to_dict") else {})
                for k, v in data_dict.items():
                    price = _extract_val(v, "last_price")
                    if price and float(price) > 0:
                        self.spot = float(price)
                        print(f"[Upstox Feed] Live NIFTY Spot: {self.spot}")
                        break

            if self.matrix:
                self.matrix.set_spot(self.spot)
                req = self.matrix.get_required_strikes()
                self.required_strikes = req["current"].union(req["next"])

            # 2. Fetch Option Contracts
            options_api = upstox_client.OptionsApi(api_client)
            res = options_api.get_option_contracts("NSE_INDEX|Nifty 50")
            contracts = res.data or []

            # Find unique sorted expiries
            expiries = sorted(list({str(c.expiry)[:10] for c in contracts}))
            self.available_expiries = expiries
            current_exp = expiries[0] if len(expiries) > 0 else ""
            next_exp = expiries[1] if len(expiries) > 1 else ""

            print(f"[Upstox Feed] Expiries detected -> Current: {current_exp}, Next: {next_exp}")

            for c in contracts:
                exp_str = str(c.expiry)[:10]
                if exp_str not in [current_exp, next_exp]:
                    continue

                expiry_tag = "current" if exp_str == current_exp else "nxt"
                strike = float(c.strike_price)
                opt_type = c.instrument_type  # 'CE' or 'PE'
                inst_key = c.instrument_key

                self.instrument_map[inst_key] = (strike, opt_type, expiry_tag)
                self.strike_to_instrument[(expiry_tag, strike, opt_type)] = inst_key
                self.strike_to_instrument[(strike, opt_type)] = inst_key

            print(f"[Upstox Feed] Mapped {len(self.instrument_map)} contracts for {current_exp} & {next_exp}.")
        except Exception as e:
            print(f"[Upstox Feed Error] Failed to fetch contracts: {e}")

    def fetch_quotes_snapshot(self) -> List[OptionQuote]:
        """
        Fetches live or closing option quotes via Upstox REST API.
        Designed for serverless Lambda environments (Vercel) without persistent WebSockets.
        """
        if not self.access_token:
            return []

        if not self.instrument_map:
            self.fetch_and_map_instruments()

        if not self.instrument_map:
            return []

        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token
        api_client = upstox_client.ApiClient(configuration)
        quote_api = upstox_client.MarketQuoteApi(api_client)

        # 1. Update spot
        try:
            ltp_res = quote_api.ltp(symbol="NSE_INDEX|Nifty 50", api_version="2.0")
            if ltp_res and ltp_res.data:
                data_dict = ltp_res.data if isinstance(ltp_res.data, dict) else (ltp_res.data.to_dict() if hasattr(ltp_res.data, "to_dict") else {})
                for k, v in data_dict.items():
                    price = _extract_val(v, "last_price")
                    if price and float(price) > 0:
                        self.spot = float(price)
                        break
            if self.matrix:
                self.matrix.set_spot(self.spot)
        except Exception as e:
            print(f"[Upstox REST] spot fetch error: {e}")

        # 2. Collect required instrument keys
        keys_to_fetch = set()
        req_strikes = self.required_strikes
        if not req_strikes and self.matrix:
            req = self.matrix.get_required_strikes()
            req_strikes = req["current"].union(req["next"])

        for strike, opt_type in req_strikes:
            for tag in ["current", "nxt"]:
                key = self.strike_to_instrument.get((tag, strike, opt_type))
                if key:
                    keys_to_fetch.add(key)

        if not keys_to_fetch:
            keys_to_fetch = set(list(self.instrument_map.keys())[:150])

        keys_list = list(keys_to_fetch)
        quotes_list: List[OptionQuote] = []

        chunk_size = 100
        for i in range(0, len(keys_list), chunk_size):
            chunk = keys_list[i:i + chunk_size]
            symbols_param = ",".join(chunk)
            try:
                res = quote_api.get_full_market_quote(symbol=symbols_param, api_version="2.0")
                if not res or not res.data:
                    continue

                data_dict = res.data if isinstance(res.data, dict) else (res.data.to_dict() if hasattr(res.data, "to_dict") else {})
                for inst_key, q_data in data_dict.items():
                    normalized_key = inst_key.replace(":", "|")
                    mapped_info = self.instrument_map.get(inst_key) or self.instrument_map.get(normalized_key)
                    if not mapped_info:
                        for k, v in self.instrument_map.items():
                            if k.endswith(inst_key) or inst_key.endswith(k):
                                mapped_info = v
                                break
                    if not mapped_info:
                        continue

                    strike, opt_type, exp_tag = mapped_info
                    ltp = float(_extract_val(q_data, "last_price", 0.0) or 0.0)
                    bid = 0.0
                    ask = 0.0
                    depth = _extract_val(q_data, "depth", None)
                    if depth:
                        buy_list = _extract_val(depth, "buy", []) or []
                        sell_list = _extract_val(depth, "sell", []) or []
                        if buy_list and len(buy_list) > 0:
                            bid = float(_extract_val(buy_list[0], "price", 0.0) or 0.0)
                        if sell_list and len(sell_list) > 0:
                            ask = float(_extract_val(sell_list[0], "price", 0.0) or 0.0)

                    # When market is closed (post 3:30 PM), order depth is 0.0.
                    # Use closing LTP with narrow spread so metrics compute accurately.
                    if (bid == 0.0 or ask == 0.0) and ltp > 0.0:
                        bid = round(max(0.05, ltp - 0.25), 2)
                        ask = round(ltp + 0.25, 2)

                    quotes_list.append(OptionQuote(
                        strike=strike,
                        option_type=opt_type,
                        bid=bid,
                        ask=ask,
                        ltp=ltp,
                        expiry=exp_tag
                    ))
            except Exception as e:
                print(f"[Upstox REST] quotes chunk error: {e}")

        if quotes_list:
            self._dispatch_batch(quotes_list)

        return quotes_list

    def start(self):
        if not self.access_token:
            raise ValueError("Upstox access_token is missing! Set UPSTOX_ACCESS_TOKEN in .env.")

        if not self.instrument_map:
            self.fetch_and_map_instruments()

        # Build list of instrument keys to subscribe
        keys_to_subscribe = set()
        for strike, opt_type in self.required_strikes:
            for tag in ["current", "nxt"]:
                key = self.strike_to_instrument.get((tag, strike, opt_type))
                if key:
                    keys_to_subscribe.add(key)

        if not keys_to_subscribe:
            keys_to_subscribe = set(list(self.instrument_map.keys())[:150])

        keys_list = list(keys_to_subscribe)
        print(f"[Upstox Feed] Initializing WebSocket streamer for {len(keys_list)} option instruments...")

        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token
        api_client = upstox_client.ApiClient(configuration)

        self.streamer = MarketDataStreamerV3(api_client)
        self.streamer.auto_reconnect(True, interval=2, retry_count=500)
        self.streamer.on(self.streamer.Event["OPEN"], self._on_open)
        self.streamer.on(self.streamer.Event["MESSAGE"], self._on_message)
        self.streamer.on(self.streamer.Event["ERROR"], self._on_error)
        self.streamer.on(self.streamer.Event["CLOSE"], self._on_close)

        # Include NIFTY 50 Index for real-time spot tracking
        if "NSE_INDEX|Nifty 50" not in keys_list:
            keys_list.append("NSE_INDEX|Nifty 50")

        self._keys_to_subscribe = keys_list
        threading.Thread(target=self.streamer.connect, daemon=True).start()

    def _on_open(self):
        print(f"[Upstox Feed] WebSocket connected! Subscribing to {len(self._keys_to_subscribe)} instruments in FULL mode...")
        self._is_connected = True
        if self._keys_to_subscribe:
            self.streamer.subscribe(self._keys_to_subscribe, self.streamer.Mode["FULL"])

    def _on_message(self, message):
        feeds = message.get("feeds", {})
        batch = []

        # Check for NIFTY Index spot update
        if "NSE_INDEX|Nifty 50" in feeds:
            nifty_feed = feeds["NSE_INDEX|Nifty 50"]
            ff = nifty_feed.get("fullFeed", {})
            idx_ff = ff.get("indexFF", {}) or ff.get("marketFF", {})
            nifty_ltp = float(idx_ff.get("ltpc", {}).get("ltp", 0.0))
            if nifty_ltp > 0:
                self.spot = nifty_ltp

        for inst_key, feed_data in feeds.items():
            if inst_key not in self.instrument_map:
                continue

            strike, opt_type, expiry_tag = self.instrument_map[inst_key]

            # Check fullFeed or marketFF
            full_feed = feed_data.get("fullFeed", {})
            market_ff = full_feed.get("marketFF", {})
            market_level = market_ff.get("marketLevel", {})
            bid_ask_quote = market_level.get("bidAskQuote", [])

            ltp = float(market_ff.get("ltpc", {}).get("ltp", 0.0))

            best_bid = 0.0
            best_ask = 0.0
            bid_qty = 0
            ask_qty = 0

            for q in bid_ask_quote:
                bp = float(q.get("bidP", 0.0))
                bq = int(q.get("bidQ", 0))
                if bp > best_bid:
                    best_bid = bp
                    bid_qty = bq

                ap = float(q.get("askP", 0.0))
                aq = int(q.get("askQ", 0))
                if ap > 0 and (best_ask == 0.0 or ap < best_ask):
                    best_ask = ap
                    ask_qty = aq

            if best_bid > 0 or best_ask > 0 or ltp > 0:
                quote = OptionQuote(
                    symbol=self.symbol,
                    strike=strike,
                    option_type=opt_type,
                    expiry=expiry_tag,
                    bid=best_bid,
                    ask=best_ask,
                    ltp=ltp,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty
                )
                batch.append(quote)
                self.dispatch_quote(quote)

        if batch:
            self.dispatch_batch(batch)

    def _on_error(self, error):
        print(f"[Upstox Feed Error] {error}")

    def _on_close(self, code, reason):
        print(f"[Upstox Feed Closed] Code: {code}, Reason: {reason}")
        self._is_connected = False

    def stop(self):
        if self.streamer:
            try:
                self.streamer.disconnect()
            except Exception:
                pass
        self._is_connected = False
