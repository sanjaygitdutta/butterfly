"""
Inspect the exact structure of Upstox index feed for NSE_INDEX|Nifty 50
"""
import os
import time
from dotenv import load_dotenv
import upstox_client
from upstox_client.feeder import MarketDataStreamerV3

load_dotenv()
access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

configuration = upstox_client.Configuration()
configuration.access_token = access_token
api_client = upstox_client.ApiClient(configuration)

streamer = MarketDataStreamerV3(api_client)

def on_open():
    print("Connected! Subscribing to NSE_INDEX|Nifty 50 and NSE_INDEX|Nifty Bank...")
    streamer.subscribe(["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"], streamer.Mode["FULL"])

def on_message(message):
    feeds = message.get("feeds", {})
    for key, data in feeds.items():
        if "Nifty 50" in key:
            print(f"\n[RECEIVED INDEX FEED FOR {key}]:")
            import json
            print(json.dumps(data, indent=2))

streamer.on(streamer.Event["OPEN"], on_open)
streamer.on(streamer.Event["MESSAGE"], on_message)

print("Starting streamer...")
import threading
threading.Thread(target=streamer.connect, daemon=True).start()

for _ in range(5):
    time.sleep(1)

streamer.disconnect()
