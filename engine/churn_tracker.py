"""
Real-time Option Strategy Churning Tracker.
Definition: One churn is completed when Highest Level CMP to Lowest Level CMP is hit.
Tracks:
- Highest Level CMP (Session Peak / Resistance)
- Lowest Level CMP (Session Trough / Support)
- Completed Churns from Highest Level to Lowest Level
- Current Phase (AT_HIGH, DROPPING_TO_LOW, AT_LOW, RISING_TO_HIGH)
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

@dataclass
class CompletedChurn:
    churn_id: int
    timestamp: float
    time_str: str
    from_level: float        # Highest Level CMP (where short was initiated)
    to_level: float          # Lowest Level CMP (where churn completed)
    points: float            # Points traversed (from_level - to_level)
    cycle_type: str = "HIGH -> LOW"
    duration_sec: float = 0.0

@dataclass
class StrikeChurnStats:
    strike: float
    combo_label: str
    churn_count: int = 0                  # Number of completed High -> Low churns
    min_price: float = float("inf")       # Lowest Level CMP
    max_price: float = float("-inf")      # Highest Level CMP
    current_price: float = 0.0
    
    # State tracking
    current_phase: str = "INITIALIZING"   # AT_HIGH, DROPPING_TO_LOW, AT_LOW, RISING_TO_HIGH
    armed_from_high: bool = False         # True when price was at Highest Level
    high_watermark: float = 0.0           # Peak price reached in this cycle
    high_timestamp: float = 0.0
    low_watermark: float = 0.0
    
    completed_churns: List[CompletedChurn] = field(default_factory=list)
    
    @property
    def price_range(self) -> float:
        if self.min_price < float("inf") and self.max_price > float("-inf"):
            return round(self.max_price - self.min_price, 2)
        return 0.0

    @property
    def avg_points(self) -> float:
        if not self.completed_churns:
            return 0.0
        return round(sum(c.points for c in self.completed_churns) / len(self.completed_churns), 2)

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "combo_label": self.combo_label,
            "churn_count": self.churn_count,
            "current_price": round(self.current_price, 2) if self.current_price else 0.0,
            "min_price": round(self.min_price, 2) if self.min_price < float("inf") else 0.0,
            "max_price": round(self.max_price, 2) if self.max_price > float("-inf") else 0.0,
            "price_range": self.price_range,
            "current_phase": self.current_phase,
            "armed_from_high": self.armed_from_high,
            "high_watermark": round(self.high_watermark, 2),
            "avg_points": self.avg_points,
            "completed_churns": [
                {
                    "churn_id": c.churn_id,
                    "time": c.time_str,
                    "from_level": round(c.from_level, 2),
                    "to_level": round(c.to_level, 2),
                    "points": round(c.points, 2),
                    "cycle_type": c.cycle_type,
                    "duration_sec": c.duration_sec
                }
                for c in self.completed_churns[-15:]
            ]
        }

class ChurnTracker:
    def __init__(self, band_tolerance: float = 0.15, min_channel_pts: float = 2.0, min_reversal_threshold: Optional[float] = None):
        """
        :param band_tolerance: Proximity in points to Highest/Lowest level to qualify as touching/hitting the level.
        :param min_channel_pts: Minimum difference between High Level and Low Level to confirm valid churn.
        """
        self.band_tolerance = band_tolerance
        self.min_channel_pts = min_reversal_threshold if min_reversal_threshold is not None else min_channel_pts
        # Key: (combo_label, strike) -> StrikeChurnStats
        self.stats: Dict[Tuple[str, float], StrikeChurnStats] = {}

    def update_price(self, combo_label: str, strike: float, price: float):
        if price is None or price == 0:
            return
            
        key = (combo_label, strike)
        if key not in self.stats:
            stats = StrikeChurnStats(
                strike=strike,
                combo_label=combo_label,
                min_price=price,
                max_price=price,
                current_price=price,
                high_watermark=price,
                low_watermark=price
            )
            self.stats[key] = stats
            return

        stats = self.stats[key]
        stats.current_price = price
        
        # 1. Update session absolute extremes
        if price < stats.min_price:
            stats.min_price = price
        if price > stats.max_price:
            stats.max_price = price

        channel_range = stats.max_price - stats.min_price
        now = time.time()

        # If channel is too narrow, still building initial range
        if channel_range < self.min_channel_pts:
            stats.current_phase = "BUILDING_RANGE"
            stats.high_watermark = stats.max_price
            return

        # 2. Check if price is at / testing the Highest Level (Peak zone)
        # Price is within band_tolerance of highest level
        is_at_highest = (price >= (stats.max_price - self.band_tolerance))
        
        # Check if price is at / hitting the Lowest Level (Trough zone)
        is_at_lowest = (price <= (stats.min_price + self.band_tolerance))

        if is_at_highest:
            stats.current_phase = "AT_HIGH"
            stats.armed_from_high = True
            if price >= stats.high_watermark or not stats.high_timestamp:
                stats.high_watermark = price
                stats.high_timestamp = now

        elif stats.armed_from_high:
            # Price has left the highest level
            drop_from_peak = stats.high_watermark - price
            
            # Case A: Price hits the Lowest Level -> ONE CHURN IS OFFICIALLY COMPLETED!
            if is_at_lowest and drop_from_peak >= self.min_channel_pts:
                time_str = time.strftime("%H:%M:%S", time.localtime(now))
                pts = round(stats.high_watermark - price, 2)
                dur = round(now - stats.high_timestamp, 1) if stats.high_timestamp else 0.0

                stats.churn_count += 1
                churn_event = CompletedChurn(
                    churn_id=stats.churn_count,
                    timestamp=now,
                    time_str=time_str,
                    from_level=round(stats.high_watermark, 2),
                    to_level=round(price, 2),
                    points=pts,
                    cycle_type="HIGH -> LOW",
                    duration_sec=dur
                )
                stats.completed_churns.append(churn_event)

                # Reset state at bottom
                stats.armed_from_high = False
                stats.high_watermark = 0.0
                stats.high_timestamp = 0.0
                stats.current_phase = "AT_LOW"
            
            # Case B: Price is on its way down towards lowest level
            elif drop_from_peak >= 0.40:
                stats.current_phase = "DROPPING_TO_LOW"

        elif is_at_lowest:
            stats.current_phase = "AT_LOW"

        else:
            # In-between levels
            if stats.current_phase == "AT_LOW" and (price > stats.min_price + 0.40):
                stats.current_phase = "RISING_TO_HIGH"

    def get_stats_for_combo(self, combo_label: str) -> List[dict]:
        res = []
        for (c_label, strike), stats in self.stats.items():
            if c_label == combo_label:
                res.append(stats.to_dict())
        res.sort(key=lambda x: (x["churn_count"], x["price_range"]), reverse=True)
        return res

    def get_all_active_churns(self, active_centers: List[float], combo_label: str = "500/200") -> List[dict]:
        res = []
        for center in active_centers:
            key = (combo_label, center)
            if key in self.stats:
                res.append(self.stats[key].to_dict())
            else:
                res.append({
                    "strike": center,
                    "combo_label": combo_label,
                    "churn_count": 0,
                    "current_price": 0.0,
                    "min_price": 0.0,
                    "max_price": 0.0,
                    "price_range": 0.0,
                    "current_phase": "INITIALIZING",
                    "armed_from_high": False,
                    "high_watermark": 0.0,
                    "avg_points": 0.0,
                    "completed_churns": []
                })
        return res
