"""
Abstract Base Class for Market Data Feeds.
"""
from abc import ABC, abstractmethod
from typing import Callable, List, Optional
from engine.combo import OptionQuote

class BaseMarketFeed(ABC):
    def __init__(self):
        self._on_quote_callbacks: List[Callable[[OptionQuote], None]] = []
        self._on_batch_callbacks: List[Callable[[List[OptionQuote]], None]] = []

    def on_quote(self, callback: Callable[[OptionQuote], None]):
        self._on_quote_callbacks.append(callback)

    def on_batch(self, callback: Callable[[List[OptionQuote]], None]):
        self._on_batch_callbacks.append(callback)

    def dispatch_quote(self, quote: OptionQuote):
        for cb in self._on_quote_callbacks:
            try:
                cb(quote)
            except Exception as e:
                print(f"[Feed Callback Error] {e}")

    def dispatch_batch(self, quotes: List[OptionQuote]):
        for cb in self._on_batch_callbacks:
            try:
                cb(quotes)
            except Exception as e:
                print(f"[Feed Batch Callback Error] {e}")

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass
