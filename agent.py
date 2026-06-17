#!/usr/bin/env python3
"""
Value Router — autonomous cross-border value delivery agent.
Parses a natural-language intent, picks the right Bitrefill product
for the destination, and purchases it autonomously (no human clicks).

Test mode: uses the 'test-gift-card-code' product — no real spend.
"""

import os
import re
import sys
import time
import json
import requests

BITREFILL_KEY = os.environ["BITREFILL_API_KEY"]
BASE = "https://api.bitrefill.com/v2"
HEADERS = {
    "Authorization": f"Bearer {BITREFILL_KEY}",
    "Content-Type": "application/json",
}

TEST_PRODUCT_ID = "test-gift-card-code"

# ── Country keyword map ────────────────────────────────────────────────────────

COUNTRY_MAP = {
    "nigeria": ("NG", "Nigeria"), "lagos": ("NG", "Nigeria"),
    "ghana": ("GH", "Ghana"), "kenya": ("KE", "Kenya"),
    "south africa": ("ZA", "South Africa"),
    "ethiopia": ("ET", "Ethiopia"),
    "philippines": ("PH", "Philippines"), "manila": ("PH", "Philippines"),
    "indonesia": ("ID", "Indonesia"), "jakarta": ("ID", "Indonesia"),
    "india": ("IN", "India"), "delhi": ("IN", "India"), "mumbai": ("IN", "India"),
    "pakistan": ("PK", "Pakistan"), "karachi": ("PK", "Pakistan"),
    "bangladesh": ("BD", "Bangladesh"),
    "brazil": ("BR", "Brazil"), "sao paulo": ("BR", "Brazil"),
    "mexico": ("MX", "Mexico"), "mexico city": ("MX", "Mexico"),
    "colombia": ("CO", "Colombia"),
    "peru": ("PE", "Peru"),
    "egypt": ("EG", "Egypt"), "cairo": ("EG", "Egypt"),
    "morocco": ("MA", "Morocco"),
    "vietnam": ("VN", "Vietnam"),
    "thailand": ("TH", "Thailand"), "bangkok": ("TH", "Thailand"),
    "united states": ("US", "United States"), "usa": ("US", "United States"),
    "uk": ("GB", "United Kingdom"), "united kingdom": ("GB", "United Kingdom"),
    "germany": ("DE", "Germany"),
    "france": ("FR", "France"),
    "canada": ("CA", "Canada"),
    "australia": ("AU", "Australia"),
    "japan": ("JP", "Japan"),
    "turkey": ("TR", "Turkey"),
    "ukraine": ("UA", "Ukraine"),
}

PRODUCT_KEYWORDS = {
    "airtime": ["airtime", "mobile", "phone", "call", "minutes", "credit", "recharge", "top up", "top-up"],
    "esim": ["esim", "e-sim", "data plan", "roaming", "travel", "landed", "landing", "trip", "abroad"],
    "gift_card": ["gift card", "amazon", "steam", "netflix", "spotify", "uber", "gaming", "shopping", "grocery"],
}

OPERATOR_MAP = {
    "NG": "MTN Nigeria", "GH": "MTN Ghana", "KE": "Safaricom Kenya",
    "ZA": "Vodacom South Africa", "ET": "Ethio Telecom",
    "PH": "Globe Philippines", "ID": "Telkomsel Indonesia",
    "IN": "Airtel India", "PK": "Jazz Pakistan", "BD": "Grameenphone",
    "BR": "Claro Brazil", "MX": "Telcel Mexico", "CO": "Claro Colombia",
    "PE": "Movistar Peru", "EG": "Vodafone Egypt", "MA": "Maroc Telecom",
    "VN": "Viettel Vietnam", "TH": "AIS Thailand",
    "US": "AT&T", "GB": "EE UK", "DE": "Telekom Germany",
    "FR": "Orange France", "CA": "Rogers Canada", "AU": "Telstra",
    "JP": "NTT Docomo", "TR": "Turkcell", "UA": "Kyivstar",
}


# ── Intent parser ──────────────────────────────────────────────────────────────

def parse_intent(intent: str) -> dict:
    text = intent.lower()

    # Detect country
    country_code, country_name = "NG", "Nigeria"  # sensible default
    for keyword, (code, name) in COUNTRY_MAP.items():
        if keyword in text:
            country_code, country_name = code, name
            break

    # Detect product type
    product_type = "airtime"  # default: most universally useful
    for ptype, keywords in PRODUCT_KEYWORDS.items():
        if any(k in text for k in keywords):
            product_type = ptype
            break

    # Detect amount
    amount = 10.0  # default $10
    match = re.search(r"\$(\d+(?:\.\d+)?)", text) or re.search(r"(\d+(?:\.\d+)?)\s*dollar", text)
    if match:
        amount = float(match.group(1))

    # Build search query
    if product_type == "airtime":
        query = OPERATOR_MAP.get(country_code, f"airtime {country_name}")
    elif product_type == "esim":
        query = f"eSIM {country_name}"
    else:
        # Try to extract a brand name for gift cards
        brands = ["amazon", "steam", "netflix", "spotify", "uber", "starbucks", "google play", "apple"]
        found = next((b for b in brands if b in text), None)
        query = f"{found} gift card" if found else f"gift card {country_name}"

    return {
        "country_code": country_code,
        "country_name": country_name,
        "product_type": product_type,
        "search_query": query,
        "amount_usd": amount,
        "reasoning": f"Detected destination: {country_name}. Best instrument: {product_type}.",
    }


# ── Bitrefill API ──────────────────────────────────────────────────────────────

def get_balance():
    r = requests.get(f"{BASE}/accounts/balance", headers=HEADERS)
    r.raise_for_status()
    return r.json()["data"]


def search_products(q: str, country_code: str = None, limit: int = 5):
    params = {"q": q, "limit": limit}
    if country_code:
        params["country"] = country_code
    r = requests.get(f"{BASE}/products/search", headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json().get("data", [])


def get_product(product_id: str):
    r = requests.get(f"{BASE}/products/{product_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()["data"]


def create_and_pay_invoice(product_id: str, value: float):
    payload = {
        "products": [{"product_id": product_id, "value": value, "quantity": 1}],
        "payment_method": "balance",
        "auto_pay": True,
    }
    r = requests.post(f"{BASE}/invoices", headers=HEADERS, json=payload)
    r.raise_for_status()
    invoice = r.json()["data"]

    # Pay immediately from balance
    pay = requests.post(f"{BASE}/invoices/{invoice['id']}/pay", headers=HEADERS, json={"payment_method": "balance"})
    pay.raise_for_status()
    return invoice["id"]


def poll_order(invoice_id: str, timeout: int = 60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/invoices/{invoice_id}", headers=HEADERS)
        r.raise_for_status()
        data = r.json()["data"]
        orders = data.get("orders", [])
        if orders and orders[0].get("status") == "delivered":
            return orders[0]
        print("   ⏳ waiting...", flush=True)
        time.sleep(3)
    raise TimeoutError("Order not delivered in time")


def test_purchase():
    """Use test product — no real spend, auto-delivers."""
    product = get_product(TEST_PRODUCT_ID)
    packages = product.get("packages", [])
    if not packages:
        raise ValueError("No packages on test product")
    value = packages[0]["value"]

    payload = {
        "products": [{"product_id": TEST_PRODUCT_ID, "value": value, "quantity": 1}],
        "payment_method": "balance",
        "auto_pay": False,
    }
    r = requests.post(f"{BASE}/invoices", headers=HEADERS, json=payload)
    r.raise_for_status()
    invoice = r.json()["data"]
    return invoice["id"], value


# ── Main agent ─────────────────────────────────────────────────────────────────

def run(intent: str, test_mode: bool = False):
    print(f"\n{'='*55}")
    print(f"  Value Router — Autonomous Cross-Border Agent")
    print(f"{'='*55}")
    print(f"\n Intent : {intent}")

    # Balance check
    bal = get_balance()
    print(f" Balance : {bal['balance']} {bal['currency']}")

    # Parse intent
    plan = parse_intent(intent)
    print(f"\n Routing plan:")
    print(f"   Destination : {plan['country_name']} ({plan['country_code']})")
    print(f"   Instrument  : {plan['product_type']}")
    print(f"   Amount      : ${plan['amount_usd']}")
    print(f"   Query       : {plan['search_query']}")
    print(f"   Reason      : {plan['reasoning']}")

    if test_mode:
        print(f"\n [TEST MODE] Using test-gift-card-code (no real spend)")
        invoice_id, value = test_purchase()
        print(f" Invoice created: {invoice_id} | value: ${value}")
        print(f"\n Polling for delivery (test products auto-deliver)...")

        # Test products deliver without payment — just poll
        deadline = time.time() + 30
        order = None
        while time.time() < deadline:
            r = requests.get(f"{BASE}/invoices/{invoice_id}", headers=HEADERS)
            data = r.json()["data"]
            orders = data.get("orders", [])
            if orders:
                order = orders[0]
                if order.get("status") == "delivered":
                    break
            print("   ⏳ waiting...", flush=True)
            time.sleep(3)

        if not order:
            print(f"\n Invoice: {invoice_id}")
            print(f" Status : payment pending (test — settle the crypto invoice to trigger delivery)")
            print(f" URL    : {data.get('payment', {}).get('uri', 'N/A')}")
            return

        redemption = order.get("redemption_info", {})
        print(f"\n {'='*40}")
        print(f"  DELIVERED!")
        print(f"  Product : {order.get('product_id', TEST_PRODUCT_ID)}")
        print(f"  Code    : {redemption.get('code', 'N/A')}")
        if redemption.get("pin"):
            print(f"  PIN     : {redemption['pin']}")
        print(f"  Order ID: {order['id']}")
        print(f" {'='*40}\n")
        return order

    # Real mode — need balance
    if bal["balance"] <= 0:
        print("\n ⚠  Balance is 0. Run with --test for test mode, or top up your account.")
        return

    # Search
    print(f"\n Searching '{plan['search_query']}' in {plan['country_name']}...")
    products = search_products(plan["search_query"], plan["country_code"])
    if not products:
        products = search_products(plan["search_query"])
    if not products:
        print(" ❌ No products found.")
        return

    # Pick best denomination
    best_product, best_value = None, None
    best_diff = float("inf")
    for p in products[:3]:
        details = get_product(p["id"])
        for pkg in details.get("packages", []):
            v = pkg.get("value", 0)
            if v <= 0:
                continue
            diff = abs(v - plan["amount_usd"])
            if diff < best_diff:
                best_diff, best_product, best_value = diff, details, v

    if not best_product:
        print(" ❌ Could not match denomination.")
        return

    print(f" Selected: {best_product['name']} — ${best_value}")

    # Purchase
    print(" Purchasing from balance (autonomous — no human click)...")
    invoice_id = create_and_pay_invoice(best_product["id"], best_value)
    print(f" Invoice: {invoice_id}")

    # Poll
    print(" Polling for delivery...")
    order = poll_order(invoice_id)
    redemption = order.get("redemption_info", {})

    print(f"\n {'='*40}")
    print(f"  DELIVERED!")
    print(f"  Product : {best_product['name']}")
    print(f"  Amount  : ${best_value}")
    print(f"  Code    : {redemption.get('code', 'N/A')}")
    if redemption.get("pin"):
        print(f"  PIN     : {redemption['pin']}")
    print(f"  Order ID: {order['id']}")
    print(f" {'='*40}\n")
    return order


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--test"]
    test = "--test" in sys.argv
    intent = " ".join(args) if args else "Send $10 of value to my friend in Nigeria"
    run(intent, test_mode=test)
