"""
Test script to verify Upstox WebSocket live streaming ticks.
"""
import time
from feed.upstox_feed import UpstoxMarketFeed
from engine.matrix import PricingMatrix

def test_stream():
    matrix = PricingMatrix()
    req = matrix.get_required_strikes()
    required = req["current"].union(req["next"])
    
    feed = UpstoxMarketFeed(required_strikes=required)
    
    ticks_count = 0
    def on_batch(quotes):
        nonlocal ticks_count
        ticks_count += len(quotes)
        print(f"[Live Tick] Received batch of {len(quotes)} quotes! Total ticks: {ticks_count}")
        for q in quotes[:2]:
            print(f"   {q.option_type} {q.strike} ({q.expiry}) -> Bid: {q.bid}, Ask: {q.ask}, LTP: {q.ltp}")
            
    feed.on_batch(on_batch)
    print("Starting Upstox Feed...")
    feed.start()
    
    # Listen for 10 seconds
    for _ in range(10):
        time.sleep(1)
        
    print(f"\nFinished! Total ticks captured: {ticks_count}")
    feed.stop()

if __name__ == "__main__":
    test_stream()
