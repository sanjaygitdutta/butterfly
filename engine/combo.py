"""
Option Quote and Combo calculation models for 6-Leg Butterfly and Straddles.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class OptionQuote:
    symbol: str
    strike: float
    option_type: str  # 'CE' or 'PE'
    expiry: str
    bid: float = 0.0
    ask: float = 0.0
    ltp: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    volume: int = 0
    oi: int = 0

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.ltp or 0.0

@dataclass
class ComboLeg:
    leg_number: int
    option_type: str  # 'CE' or 'PE'
    strike: float
    action: str  # 'BUY' or 'SELL'
    ratio: int  # 1 or 2
    is_bidding: bool = False
    quote: Optional[OptionQuote] = None

@dataclass
class ComboResult:
    center: float
    gap: int
    wing: int
    label: str
    legs: List[ComboLeg]
    bcmp: Optional[float] = None  # Buy price (negative debit, e.g. -71.0)
    scmp: Optional[float] = None  # Sell price (positive credit, e.g. +70.0)
    spread: Optional[float] = None # Spread |bcmp| - scmp
    is_valid: bool = False

def generate_6leg_butterfly(center: float, gap: int, wing: int, quotes_map: Dict[str, OptionQuote], expiry: str = "") -> ComboResult:
    """
    Constructs the 6 legs for PE-CE BTFLY and computes BCmp & SCmp.
    
    Center = C
    Gap = G
    Wing = W (BTFLY)
    
    PE Center = C - G / 2
    PE Leg 1 (Buy 1): C - G / 2 - W
    PE Leg 2 (Sell 2): C - G / 2
    PE Leg 3 (Buy 1): C - G / 2 + W  [Bidding Leg]
    
    CE Center = C + G / 2
    CE Leg 4 (Buy 1): C + G / 2 - W
    CE Leg 5 (Sell 2): C + G / 2
    CE Leg 6 (Buy 1): C + G / 2 + W
    """
    pe_mid = center - (gap / 2.0)
    ce_mid = center + (gap / 2.0)
    
    strikes = [
        ("PE", pe_mid - wing, "BUY", 1, False),   # Leg 1
        ("PE", pe_mid, "SELL", 2, False),         # Leg 2
        ("PE", pe_mid + wing, "BUY", 1, True),    # Leg 3 (Bidding Leg)
        ("CE", ce_mid - wing, "BUY", 1, False),   # Leg 4
        ("CE", ce_mid, "SELL", 2, False),         # Leg 5
        ("CE", ce_mid + wing, "BUY", 1, False),   # Leg 6
    ]
    
    legs: List[ComboLeg] = []
    all_quotes_valid = True
    
    for idx, (opt_type, strike, action, ratio, is_bid) in enumerate(strikes, start=1):
        key = f"{expiry}_{int(strike)}_{opt_type}" if expiry else f"{int(strike)}_{opt_type}"
        quote = quotes_map.get(key)
        
        if not quote or quote.bid <= 0 or quote.ask <= 0:
            all_quotes_valid = False
            
        legs.append(ComboLeg(
            leg_number=idx,
            option_type=opt_type,
            strike=strike,
            action=action,
            ratio=ratio,
            is_bidding=is_bid,
            quote=quote
        ))
        
    bcmp = None
    scmp = None
    spread = None
    
    if all_quotes_valid:
        # Leg 1: PE Buy at Ask
        # Leg 2: PE Sell at Bid (x2)
        # Leg 3: PE Buy at Ask
        # Leg 4: CE Buy at Ask
        # Leg 5: CE Sell at Bid (x2)
        # Leg 6: CE Buy at Ask
        q1 = legs[0].quote
        q2 = legs[1].quote
        q3 = legs[2].quote
        q4 = legs[3].quote
        q5 = legs[4].quote
        q6 = legs[5].quote
        
        buy_cost = (
            (1 * q1.ask) - (2 * q2.bid) + (1 * q3.ask) +
            (1 * q4.ask) - (2 * q5.bid) + (1 * q6.ask)
        )
        # In terminal convention, BCmp is cashflow debit (negative)
        bcmp = round(-buy_cost, 2)
        
        # Sell Combo:
        # Leg 1: PE Sell at Bid
        # Leg 2: PE Buy at Ask (x2)
        # Leg 3: PE Sell at Bid
        # Leg 4: CE Sell at Bid
        # Leg 5: CE Buy at Ask (x2)
        # Leg 6: CE Sell at Bid
        sell_credit = (
            (1 * q1.bid) - (2 * q2.ask) + (1 * q3.bid) +
            (1 * q4.bid) - (2 * q5.ask) + (1 * q6.bid)
        )
        scmp = round(sell_credit, 2)
        spread = round(abs(bcmp) - scmp, 2)
        
    return ComboResult(
        center=center,
        gap=gap,
        wing=wing,
        label=f"{gap}/{wing}",
        legs=legs,
        bcmp=bcmp,
        scmp=scmp,
        spread=spread,
        is_valid=all_quotes_valid
    )

def calculate_straddle(center: float, quotes_map: Dict[str, OptionQuote], expiry: str = "") -> Dict[str, Optional[float]]:
    """
    Calculates Straddle price (CE + PE) and 1-2 Ratio for a given strike.
    """
    ce_key = f"{expiry}_{int(center)}_CE" if expiry else f"{int(center)}_CE"
    pe_key = f"{expiry}_{int(center)}_PE" if expiry else f"{int(center)}_PE"
    
    ce = quotes_map.get(ce_key)
    pe = quotes_map.get(pe_key)
    
    if ce and pe and (ce.ask > 0 or ce.ltp > 0) and (pe.ask > 0 or pe.ltp > 0):
        ce_ask = ce.ask if ce.ask > 0 else ce.ltp
        pe_ask = pe.ask if pe.ask > 0 else pe.ltp
        ce_bid = ce.bid if ce.bid > 0 else ce.ltp
        pe_bid = pe.bid if pe.bid > 0 else pe.ltp

        straddle_buy = round(ce_ask + pe_ask, 2)
        straddle_sell = round(ce_bid + pe_bid, 2)
        
        # 1-2 Column in Excel: Straddle Sell / Extrinsic credit
        ratio_1_2 = round(-straddle_sell, 2)
        
        return {
            "straddle": straddle_buy,
            "straddle_sell": straddle_sell,
            "ratio_1_2": ratio_1_2,
            "is_valid": True
        }
    return {
        "straddle": None,
        "straddle_sell": None,
        "ratio_1_2": None,
        "is_valid": False
    }
