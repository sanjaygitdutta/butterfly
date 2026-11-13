"""
Realistic NIFTY Options Market Data Simulator.
Generates live streaming quotes modeled after market conditions in Screenshot 2 and Screenshot 3.
Spot ~ 23135.4, realistic Greeks and bid-ask spreads.
"""
import math
import random
import threading
import time
from typing import List, Set, Tuple
from .base import BaseMarketFeed
from engine.combo import OptionQuote

def normal_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def black_scholes_price(spot: float, strike: float, t: float, r: float, sigma: float, option_type: str) -> float:
    if t <= 0.0001:
        if option_type == "CE":
            return max(0.0, spot - strike)
        else:
            return max(0.0, strike - spot)
            
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    
    if option_type == "CE":
        price = spot * normal_cdf(d1) - strike * math.exp(-r * t) * normal_cdf(d2)
    else:
        price = strike * math.exp(-r * t) * normal_cdf(-d2) - spot * normal_cdf(-d1)
        
    return max(0.05, price)

class SimulatorFeed(BaseMarketFeed):
    def __init__(
        self,
        required_strikes: Set[Tuple[float, str]],
        initial_spot: float = 25299.0,
        tick_interval: float = 0.5
    ):
        super().__init__()
        self.required_strikes = required_strikes
        self.spot = initial_spot
        self.tick_interval = tick_interval
        self._running = False
        self._thread: threading.Thread = None
        
        # Supported expiries and days to expiry
        self.expiries = [
            ("current", 3.5),
            ("nxt", 10.5)
        ]
        self.risk_free_rate = 0.065
        self.base_iv = 0.138  # ~13.8% IV
        
    def _calculate_iv(self, strike: float) -> float:
        # Volatility smile / skew: OTM Puts have higher IV
        moneyness = math.log(strike / self.spot)
        skew = -0.15 * moneyness + 0.3 * (moneyness ** 2)
        return max(0.08, self.base_iv + skew)

    def generate_all_quotes(self) -> List[OptionQuote]:
        quotes = []
        for exp_tag, dte in self.expiries:
            t = dte / 365.0
            for strike, opt_type in self.required_strikes:
                iv = self._calculate_iv(strike)
                theo = black_scholes_price(self.spot, strike, t, self.risk_free_rate, iv, opt_type)
                
                # Realistic spread: 0.20 to 0.80 pts depending on premium
                spread = max(0.15, round(min(1.5, theo * 0.015), 2))
                half_spread = spread / 2.0
                
                bid = round(max(0.05, theo - half_spread), 2)
                ask = round(bid + spread, 2)
                ltp = round(random.choice([bid, ask, (bid + ask) / 2.0]), 2)
                
                quotes.append(OptionQuote(
                    symbol="NIFTY",
                    strike=float(strike),
                    option_type=opt_type,
                    expiry=exp_tag,
                    bid=bid,
                    ask=ask,
                    ltp=ltp,
                    bid_qty=random.randint(5, 50) * 65,
                    ask_qty=random.randint(5, 50) * 65,
                    volume=random.randint(1000, 50000),
                    oi=random.randint(5000, 200000)
                ))
        return quotes

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        # Initial batch dispatch
        initial_quotes = self.generate_all_quotes()
        self.dispatch_batch(initial_quotes)
        
        while self._running:
            time.sleep(self.tick_interval)
            
            # Subtle random walk in spot (e.g. +/- 0.5 to 2 points)
            drift = random.gauss(0, 0.4)
            self.spot = round(self.spot + drift, 2)
            
            # Pick a subset of strikes to update each tick
            sample_size = min(len(self.required_strikes), random.randint(15, 30))
            selected = random.sample(list(self.required_strikes), sample_size)
            
            batch = []
            for exp_tag, dte in self.expiries:
                t = dte / 365.0
                for strike, opt_type in selected:
                    iv = self._calculate_iv(strike)
                    theo = black_scholes_price(self.spot, strike, t, self.risk_free_rate, iv, opt_type)
                    
                    spread = max(0.15, round(min(1.5, theo * 0.015), 2))
                    bid = round(max(0.05, theo - spread / 2.0), 2)
                    ask = round(bid + spread, 2)
                    ltp = round(random.choice([bid, ask, (bid + ask) / 2.0]), 2)
                    
                    q = OptionQuote(
                        symbol="NIFTY",
                        strike=float(strike),
                        option_type=opt_type,
                        expiry=exp_tag,
                        bid=bid,
                        ask=ask,
                        ltp=ltp,
                        bid_qty=random.randint(5, 40) * 65,
                        ask_qty=random.randint(5, 40) * 65
                    )
                    batch.append(q)
                    self.dispatch_quote(q)
                    
            self.dispatch_batch(batch)
