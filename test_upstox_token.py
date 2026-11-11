"""
Quick test script to verify Upstox Access Token and API connectivity.
"""
import os
from dotenv import load_dotenv
import upstox_client
from upstox_client.rest import ApiException

load_dotenv()

access_token = os.getenv("UPSTOX_ACCESS_TOKEN", "")

def test_connection():
    print(f"Testing Upstox token: {access_token[:12]}...{access_token[-8:]}")
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_client = upstox_client.ApiClient(configuration)
    
    # 1. Test User Profile API
    user_api = upstox_client.UserApi(api_client)
    try:
        profile_res = user_api.get_profile("2.0")
        print("Profile Response Status:", profile_res.status)
        user_name = profile_res.data.user_name if profile_res.data else "Unknown"
        user_id = profile_res.data.user_id if profile_res.data else "Unknown"
        print(f"Successfully authenticated as: {user_name} (ID: {user_id})")
    except ApiException as e:
        print(f"User Profile API error: {e}")
        return False

    # 2. Test Market Quote API on NIFTY index
    quote_api = upstox_client.MarketQuoteApi(api_client)
    try:
        quote_res = quote_api.get_market_quote_last_traded_price("NSE_INDEX|Nifty 50", "2.0")
        print("Market Quote API Status:", quote_res.status)
        if quote_res.data:
            key = list(quote_res.data.keys())[0]
            ltp = quote_res.data[key].last_price
            print(f"Live NIFTY 50 Spot Price from Upstox: {ltp}")
    except ApiException as e:
        print(f"Market Quote API error: {e}")

    return True

if __name__ == "__main__":
    test_connection()
