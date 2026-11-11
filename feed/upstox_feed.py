"""
Live Upstox API v2 / v3 Market Data WebSocket Feed.
Connects using upstox-python-sdk MarketDataStreamerV3 with Protobuf decoding.
Maps NIFTY option contracts directly via Upstox OptionsApi.
"""
import os
import threading
from typing import Dict, List, Set, Tuple, Optional, Any
import upstox_client
from upstox_client.feeder import MarketDataStreamerV3
from .base import BaseMarketFeed
from engine.combo import OptionQuote
from config import upstox_config

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
        
        # Spot price tracking
        self.spot: float = 25255.0
        
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
                for k, v in ltp_res.data.items():
                    if hasattr(v, "last_price"):
                        self.spot = float(v.last_price)
                        print(f"[Upstox Feed] Live NIFTY Spot: {self.spot}")

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
