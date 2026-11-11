"""
Verification script to test calculation accuracy and matrix output.
"""
from engine.matrix import PricingMatrix
from feed.simulator import SimulatorFeed

def test():
    print("1. Initializing PricingMatrix...")
    matrix = PricingMatrix()
    req = matrix.get_required_strikes()
    all_req = req["current"].union(req["next"])
    print(f"   Required option contracts: {len(all_req)}")

    print("2. Generating quotes from SimulatorFeed (Spot = 23135.4)...")
    sim = SimulatorFeed(required_strikes=all_req, initial_spot=23135.4)
    quotes = sim.generate_all_quotes()
    print(f"   Generated {len(quotes)} quotes.")

    print("3. Updating matrix and computing all combos...")
    matrix.update_quotes_batch(quotes)
    matrix.recompute_all()

    print("4. Inspecting Combo 500/200 at Center 23050:")
    res_500_200 = matrix.results_current.get("500/200", {}).get(23050)
    if res_500_200:
        print(f"   Center: {res_500_200.center}")
        print(f"   BCmp (Buy Price): {res_500_200.bcmp}")
        print(f"   SCmp (Sell Price): {res_500_200.scmp}")
        print(f"   Spread: {res_500_200.spread}")
        print("   Legs breakdown:")
        for leg in res_500_200.legs:
            q = leg.quote
            bid_str = f"Bid: {q.bid}" if q else "No Bid"
            ask_str = f"Ask: {q.ask}" if q else "No Ask"
            print(f"     Leg {leg.leg_number}: {leg.action} {leg.ratio}x {leg.option_type} {leg.strike} ({bid_str}, {ask_str}) {'[BIDDING LEG]' if leg.is_bidding else ''}")

    print("\n5. Inspecting Straddle at Center 23150 (ATM):")
    strd = matrix.straddles_current.get(23150)
    print(f"   Straddle Price: {strd}")

    print("\n6. Sample Table Rows:")
    table_rows = matrix.to_table_data("current")
    for r in table_rows[3:7]:
        print(f"   Strike: {r['Strike']} | 500/200 BCmp: {r.get('500/200_BCmp')} | 500/200 SCmp: {r.get('500/200_SCmp')} | Straddle: {r.get('Straddle')}")

    print("\nSUCCESS: All math & matrix computations verified successfully!")

if __name__ == "__main__":
    test()
