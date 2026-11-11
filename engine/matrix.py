"""
Pricing Matrix Engine with Dynamic ATM Centering (ATM +/- 7 strikes real-time sliding window).
"""
from typing import Dict, List, Tuple, Any, Optional
from .combo import OptionQuote, ComboResult, generate_6leg_butterfly, calculate_straddle
from .churn_tracker import ChurnTracker
from config import engine_config

class PricingMatrix:
    def __init__(
        self,
        initial_spot: float = 23100.0,
        strikes_above_below: int = engine_config.strikes_above_below,
        step: int = engine_config.strike_step,
        combos_current: Optional[List[Tuple[int, int, str]]] = None,
        combos_next: Optional[List[Tuple[int, int, str]]] = None,
        current_expiry: str = "current",
        next_expiry: str = "nxt"
    ):
        self.step = step
        self.strikes_above_below = strikes_above_below
        self.spot = initial_spot
        self.atm = int(round(initial_spot / self.step) * self.step)
        
        # 10 strikes below ATM, ATM, 10 strikes above ATM -> 21 rows
        self.centers = [self.atm + (i * self.step) for i in range(-self.strikes_above_below, self.strikes_above_below + 1)]
        
        self.combos_current = combos_current or engine_config.combos_current
        self.combos_next = combos_next or engine_config.combos_next
        self.current_expiry = current_expiry
        self.next_expiry = next_expiry
        
        # Real-time Churning Tracker (Strict High Level detection)
        self.churn_tracker = ChurnTracker(band_tolerance=0.15, min_channel_pts=2.0)
        
        # Real-time SCmp Peak / High Level Detector for Sell Signals
        # Key: (combo_label, center) -> {"min": float, "max": float, "last": float, "peak": bool}
        self.scmp_extremes: Dict[Tuple[str, float], Dict[str, Any]] = {}
        
        # Cache for quotes: key is f"{expiry}_{strike}_{opt_type}" or f"{strike}_{opt_type}"
        self.quotes_map: Dict[str, OptionQuote] = {}
        
        # Computed results
        self.results_current: Dict[str, Dict[float, ComboResult]] = {}
        self.results_next: Dict[str, Dict[float, ComboResult]] = {}
        self.straddles_current: Dict[float, Dict[str, Optional[float]]] = {}

    def set_spot(self, spot: float):
        """
        Updates spot price in real time. If ATM shifts, slides the 15-strike window dynamically.
        """
        if spot <= 0:
            return
        self.spot = spot
        new_atm = int(round(spot / self.step) * self.step)
        if new_atm != self.atm:
            print(f"[PricingMatrix] ATM Strike Shifted: {self.atm} -> {new_atm} (Spot: {spot})")
            self.atm = new_atm
            self.centers = [self.atm + (i * self.step) for i in range(-self.strikes_above_below, self.strikes_above_below + 1)]
            self.recompute_all()

    def get_required_strikes(self) -> Dict[str, set]:
        """
        Determines all unique (strike, option_type) required for subscription.
        Covers a wide range (+/- 25 strikes around spot) to ensure no dropped subscriptions during intraday trends.
        """
        req_current = set()
        req_next = set()
        
        base_atm = int(round(self.spot / self.step) * self.step)
        extended_centers = [base_atm + (i * self.step) for i in range(-25, 26)]
        
        for center in extended_centers:
            # Current expiry combos
            for gap, wing, _ in self.combos_current:
                pe_mid = center - (gap / 2.0)
                ce_mid = center + (gap / 2.0)
                req_current.add((pe_mid - wing, "PE"))
                req_current.add((pe_mid, "PE"))
                req_current.add((pe_mid + wing, "PE"))
                req_current.add((ce_mid - wing, "CE"))
                req_current.add((ce_mid, "CE"))
                req_current.add((ce_mid + wing, "CE"))
                
            # Next expiry combos
            for gap, wing, _ in self.combos_next:
                pe_mid = center - (gap / 2.0)
                ce_mid = center + (gap / 2.0)
                req_next.add((pe_mid - wing, "PE"))
                req_next.add((pe_mid, "PE"))
                req_next.add((pe_mid + wing, "PE"))
                req_next.add((ce_mid - wing, "CE"))
                req_next.add((ce_mid, "CE"))
                req_next.add((ce_mid + wing, "CE"))
                
            # Straddles
            req_current.add((center, "CE"))
            req_current.add((center, "PE"))
            
        return {
            "current": req_current,
            "next": req_next
        }
        
    def update_quote(self, quote: OptionQuote):
        key = f"{quote.expiry}_{int(quote.strike)}_{quote.option_type}"
        self.quotes_map[key] = quote
        if quote.expiry == self.current_expiry or not quote.expiry:
            self.quotes_map[f"{int(quote.strike)}_{quote.option_type}"] = quote

    def update_quotes_batch(self, quotes: List[OptionQuote]):
        for q in quotes:
            self.update_quote(q)

    def _update_and_check_scmp_peak(self, label: str, center: float, scmp: float) -> bool:
        """
        Evaluates whether current SCmp is genuinely at a High Level (Sell Signal).
        Conditions for authentic High Level Sell Signal:
        1. A meaningful trading range has developed (at least 2.0 pts or 5% of CMP, preventing 50-paise noise).
        2. Current SCmp is strictly at or testing the High Level (within 0.15 pts of the peak).
        3. Current SCmp is in the top 8% of the trading channel ((price - min) / range >= 0.92).
        4. ChurnTracker confirms the strike is actively in AT_HIGH phase (not dropping or building range).
        """
        ext = self.scmp_extremes.setdefault((label, center), {
            "min": scmp,
            "max": scmp,
            "last": scmp,
            "peak": False,
            "updates": 0
        })
        ext["updates"] = ext.get("updates", 0) + 1
        if scmp > ext["max"]:
            ext["max"] = scmp
        if scmp < ext["min"]:
            ext["min"] = scmp
        ext["last"] = scmp

        rng = ext["max"] - ext["min"]
        min_required_range = max(2.0, min(3.5, ext["max"] * 0.05))

        c_stat = self.churn_tracker.stats.get((label, center))

        # Check if strictly at High Level
        if rng >= min_required_range and (scmp >= (ext["max"] - 0.15)) and ((scmp - ext["min"]) / rng >= 0.92):
            if c_stat and c_stat.current_phase in ("DROPPING_TO_LOW", "AT_LOW"):
                is_peak = False
            else:
                is_peak = True
        else:
            is_peak = False

        ext["peak"] = is_peak
        return is_peak

    def recompute_all(self):
        """
        Recomputes all combos for the active centers (ATM +/- 7 strikes).
        """
        # Current Expiry
        for gap, wing, label in self.combos_current:
            if label not in self.results_current:
                self.results_current[label] = {}
            for center in self.centers:
                res = generate_6leg_butterfly(center, gap, wing, self.quotes_map, expiry=self.current_expiry)
                self.results_current[label][center] = res
                if res.is_valid and res.scmp is not None:
                    self.churn_tracker.update_price(label, center, res.scmp)
                    self._update_and_check_scmp_peak(label, center, res.scmp)

        # Next Expiry
        for gap, wing, label in self.combos_next:
            if label not in self.results_next:
                self.results_next[label] = {}
            for center in self.centers:
                res = generate_6leg_butterfly(center, gap, wing, self.quotes_map, expiry=self.next_expiry)
                self.results_next[label][center] = res
                if res.is_valid and res.scmp is not None:
                    self.churn_tracker.update_price(label, center, res.scmp)
                    self._update_and_check_scmp_peak(label, center, res.scmp)

        # Straddles
        for center in self.centers:
            self.straddles_current[center] = calculate_straddle(center, self.quotes_map, expiry=self.current_expiry)

    def to_table_data(self, section: str = "current") -> List[Dict[str, Any]]:
        rows = []
        combos = self.combos_current if section == "current" else self.combos_next
        results = self.results_current if section == "current" else self.results_next

        for center in self.centers:
            is_atm = (center == self.atm)
            row: Dict[str, Any] = {
                "Strike": center,
                "is_atm": is_atm,
                "offset_from_atm": int((center - self.atm) / self.step)
            }
            for _, _, label in combos:
                res = results.get(label, {}).get(center)
                ext = self.scmp_extremes.get((label, center), {})
                c_combo_stats = self.churn_tracker.stats.get((label, center))
                if res and res.is_valid:
                    row[f"{label}_BCmp"] = res.bcmp
                    row[f"{label}_SCmp"] = res.scmp
                    row[f"{label}_SCmp_Peak"] = ext.get("peak", False)
                    row[f"{label}_SCmp_Max"] = round(ext.get("max", 0.0), 2)
                    row[f"{label}_SCmp_Min"] = round(ext.get("min", 0.0), 2)
                else:
                    row[f"{label}_BCmp"] = "-"
                    row[f"{label}_SCmp"] = "-"
                    row[f"{label}_SCmp_Peak"] = False

                if c_combo_stats and (c_combo_stats.churn_count > 0 or c_combo_stats.min_price < float("inf")):
                    row[f"{label}_churn_count"] = c_combo_stats.churn_count
                    row[f"{label}_churn_min"] = round(c_combo_stats.min_price, 2)
                    row[f"{label}_churn_max"] = round(c_combo_stats.max_price, 2)
                    row[f"{label}_churn_range"] = c_combo_stats.price_range
                    row[f"{label}_churn_phase"] = c_combo_stats.current_phase
                else:
                    row[f"{label}_churn_count"] = 0
                    row[f"{label}_churn_min"] = 0.0
                    row[f"{label}_churn_max"] = 0.0
                    row[f"{label}_churn_range"] = 0.0
                    row[f"{label}_churn_phase"] = "INITIALIZING"

            if section == "current":
                strd = self.straddles_current.get(center, {})
                row["Straddle"] = strd.get("straddle", "-")

            # Default fallback churn stats (500/200 for current, combos_next[0] for next)
            default_combo = "500/200" if section == "current" else (self.combos_next[0][2] if self.combos_next else "1000/300 Nxt")
            c_stats = self.churn_tracker.stats.get((default_combo, center))
            if c_stats and (c_stats.churn_count > 0 or c_stats.min_price < float("inf")):
                row["churn_count"] = c_stats.churn_count
                row["churn_min"] = round(c_stats.min_price, 2)
                row["churn_max"] = round(c_stats.max_price, 2)
                row["churn_range"] = c_stats.price_range
                row["churn_phase"] = c_stats.current_phase
                row["churn_armed"] = c_stats.armed_from_high
                row["churn_avg_pts"] = c_stats.avg_points
            else:
                row["churn_count"] = 0
                row["churn_min"] = 0.0
                row["churn_max"] = 0.0
                row["churn_range"] = 0.0
                row["churn_phase"] = "INITIALIZING"
                row["churn_armed"] = False
                row["churn_avg_pts"] = 0.0

            rows.append(row)
        return rows
