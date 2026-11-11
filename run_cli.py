"""
CLI Runner for the Butterfly Pricing Engine.
Displays real-time updating matrix in the terminal using Rich Live display.
"""
import argparse
import time
import sys
from rich.console import Console
from rich.live import Live
from engine.matrix import PricingMatrix
from feed.simulator import SimulatorFeed
from feed.upstox_feed import UpstoxMarketFeed
from display.terminal_table import render_dashboard
from config import upstox_config, engine_config

def main():
    parser = argparse.ArgumentParser(description="Fractal 6-Leg Butterfly Real-Time Pricing Engine")
    parser.add_argument("--mode", choices=["sim", "upstox"], default="sim", help="Feed mode: sim (realistic simulator) or upstox (live broker)")
    parser.add_argument("--expiry", choices=["current", "next"], default="current", help="Expiry to display: current or next")
    parser.add_argument("--token", default=upstox_config.access_token, help="Upstox Access Token")
    parser.add_argument("--interval", type=float, default=0.5, help="Refresh interval in seconds")
    args = parser.parse_args()

    console = Console()
    console.print("[bold green]Initializing Pricing Engine...[/bold green]")

    matrix = PricingMatrix()
    req = matrix.get_required_strikes()
    required_strikes = req["current"].union(req["next"])

    feed_type = "Simulator (NIFTY ~23135)"
    spot_val = 23135.4

    if args.mode == "upstox":
        if not args.token:
            console.print("[bold red]Error: Upstox access token is missing![/bold red]")
            console.print("Please set UPSTOX_ACCESS_TOKEN in .env or pass --token <token>")
            console.print("Falling back to Simulator mode...\n")
            args.mode = "sim"
        else:
            feed_type = "Upstox Live WebSocket"
            feed = UpstoxMarketFeed(access_token=args.token, required_strikes=required_strikes)

    if args.mode == "sim":
        feed = SimulatorFeed(required_strikes=required_strikes, initial_spot=spot_val, tick_interval=args.interval)

    # Attach feed callbacks
    def on_batch(quotes):
        matrix.update_quotes_batch(quotes)
        matrix.recompute_all()

    feed.on_batch(on_batch)

    console.print(f"[bold cyan]Subscribing to {len(required_strikes)} option strikes...[/bold cyan]")
    feed.start()

    # Allow initial quotes to populate
    time.sleep(1.0)
    matrix.recompute_all()

    console.print("[bold green]Starting Real-Time Dashboard. Press Ctrl+C to exit.[/bold green]\n")

    try:
        with Live(render_dashboard(matrix, spot=getattr(feed, 'spot', spot_val), feed_type=feed_type, section=args.expiry), console=console, refresh_per_second=4, screen=False) as live:
            while True:
                time.sleep(args.interval)
                current_spot = getattr(feed, 'spot', spot_val)
                live.update(render_dashboard(matrix, spot=current_spot, feed_type=feed_type, section=args.expiry))
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping feed and exiting...[/yellow]")
        feed.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()
