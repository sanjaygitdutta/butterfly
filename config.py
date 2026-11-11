"""
Configuration settings for Butterfly Pricing Engine.
"""
import os
from dataclasses import dataclass, field
from typing import List, Tuple
from dotenv import load_dotenv

load_dotenv()

@dataclass
class UpstoxConfig:
    api_key: str = os.getenv("UPSTOX_API_KEY", "")
    api_secret: str = os.getenv("UPSTOX_API_SECRET", "")
    redirect_uri: str = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")
    access_token: str = os.getenv("UPSTOX_ACCESS_TOKEN", "")

@dataclass
class EngineConfig:
    symbol: str = "NIFTY"
    strike_step: int = 50
    center_min: int = 22850
    strikes_above_below: int = 10
    default_lot_size: int = 65
    
    # Strategy Combos: Tuple of (Gap, Wing, Label)
    combos_current: List[Tuple[int, int, str]] = field(default_factory=lambda: [
        (1000, 500, "1000/500"),
        (1000, 400, "1000/400"),
        (1000, 300, "1000/300"),
        (900, 400, "900/400"),
        (900, 300, "900/300"),
        (800, 300, "800/300"),
        (700, 300, "700/300"),
        (700, 200, "700/200"),
        (600, 300, "600/300"),
        (600, 200, "600/200"),
        (500, 200, "500/200"),
        (400, 200, "400/200"),
    ])
    
    combos_next: List[Tuple[int, int, str]] = field(default_factory=lambda: [
        (1500, 600, "1500/600 nxt"),
        (1500, 500, "1500/500 nxt"),
        (1500, 400, "1500/400 nxt"),
        (1400, 600, "1400/600 nxt"),
        (1400, 500, "1400/500 nxt"),
        (1400, 400, "1400/400 nxt"),
        (1300, 600, "1300/600 nxt"),
        (1300, 500, "1300/500 nxt"),
        (1300, 400, "1300/400 nxt"),
        (1200, 600, "1200/600 nxt"),
        (1200, 500, "1200/500 nxt"),
        (1200, 400, "1200/400 nxt"),
        (1200, 300, "1200/300 nxt"),
        (1100, 600, "1100/600 nxt"),
        (1100, 500, "1100/500 nxt"),
        (1100, 400, "1100/400 nxt"),
        (1100, 300, "1100/300 nxt"),
        (1000, 600, "1000/600 nxt"),
        (1000, 500, "1000/500 nxt"),
        (1000, 400, "1000/400 nxt"),
        (1000, 300, "1000/300 nxt"),
        (900, 600, "900/600 nxt"),
        (900, 500, "900/500 nxt"),
        (900, 400, "900/400 nxt"),
        (900, 300, "900/300 nxt"),
        (800, 300, "800/300 nxt"),
        (700, 300, "700/300 nxt"),
        (400, 200, "400/200 nxt"),
    ])

upstox_config = UpstoxConfig()
engine_config = EngineConfig()
