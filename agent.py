#!/usr/bin/env python3
"""
Value Router — autonomous cross-border value delivery agent.

Single mode:  one intent, one country, one purchase.
Team mode:    parse multiple recipients, route each independently,
              settle in ONE multi-product invoice (no human clicks).

Usage:
  python agent.py "Send $10 to my brother in Lagos"
  python agent.py "Send $10 to my brother in Lagos" --test
  python agent.py --team "Alice in Lagos $10, Bob in Manila $15, Carlos in Mexico City $10" --test
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

# ── Country map ────────────────────────────────────────────────────────────────

COUNTRY_MAP = {
    "nigeria": ("NG", "Nigeria"), "lagos": ("NG", "Nigeria"), "abuja": ("NG", "Nigeria"),
    "ghana": ("GH", "Ghana"), "accra": ("GH", "Ghana"),
    "kenya": ("KE", "Kenya"), "nairobi": ("KE", "Kenya"),
    "south africa": ("ZA", "South Africa"), "johannesburg": ("ZA", "South Africa"),
    "ethiopia": ("ET", "Ethiopia"), "addis": ("ET", "Ethiopia"),
    "philippines": ("PH", "Philippines"), "manila": ("PH", "Philippines"),
    "indonesia": ("ID", "Indonesia"), "jakarta": ("ID", "Indonesia"),
    "india": ("IN", "India"), "delhi": ("IN", "India"), "mumbai": ("IN", "India"),
    "pakistan": ("PK", "Pakistan"), "karachi": ("PK", "Pakistan"),
    "bangladesh": ("BD", "Bangladesh"), "dhaka": ("BD", "Bangladesh"),
    "brazil": ("BR", "Brazil"), "sao paulo": ("BR", "Brazil"),
    "mexico": ("MX", "Mexico"), "mexico city": ("MX", "Mexico"),
    "colombia": ("CO", "Colombia"), "bogota": ("CO", "Colombia"),
    "peru": ("PE", "Peru"), "lima": ("PE", "Peru"),
    "egypt": ("EG", "Egypt"), "cairo": ("EG", "Egypt"),
    "morocco": ("MA", "Morocco"), "casablanca": ("MA", "Morocco"),
    "vietnam": ("VN", "Vietnam"), "hanoi": ("VN", "Vietnam"),
    "thailand": ("TH", "Thailand"), "bangkok": ("TH", "Thailand"),
    "united states": ("US", "United States"), "usa": ("US", "United States"),
    "uk": ("GB", "United Kingdom"), "united kingdom": ("GB", "United Kingdom"), "london": ("GB", "United Kingdom"),
    "germany": ("DE", "Germany"), "berlin": ("DE", "Germany"),
    "france": ("FR", "France"), "paris": ("FR", "France"),
    "canada": ("CA", "Canada"), "toronto": ("CA", "Canada"),
    "australia": ("AU", "Australia"), "sydney": ("AU", "Australia"),
    "japan": ("JP", "Japan"), "tokyo": ("JP", "Japan"),
    "turkey": ("TR", "Turkey"), "istanbul": ("TR", "Turkey"),
    "ukraine": ("UA", "Ukraine"), "kyiv": ("UA", "Ukraine"),
    "venezuela": ("VE", "Venezuela"), "caracas": ("VE", "Venezuela"),
    "zimbabwe": ("ZW", "Zimbabwe"), "harare": ("ZW", "Zimbabwe"),
    "senegal": ("SN", "Senegal"), "dakar": ("SN", "Senegal"),
    "tanzania": ("TZ", "Tanzania"), "dar es salaam": ("TZ", "Tanzania"),
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
    "VE": "Movilnet Venezuela", "ZW": "Econet Zimbabwe",
    "SN": "Orange Senegal", "TZ": "Vodacom Tanzania",
}

PRODUCT_KEYWORDS = {
    "esim":      ["esim", "e-sim", "data plan", "roaming", "travel", "landed", "landing", "trip", "abroad"],
    "gift_card": ["gift card", "amazon", "steam", "netflix", "spotify", "uber", "gaming", "shopping", "grocery"],
    "airtime":   ["airtime", "mobile", "phone", "call", "minutes", "credit", "recharge", "top up", "top-up"],
}

GIFT_CARD_BRANDS = ["amazon", "steam", "netflix", "spotify", "uber", "starbucks", "google play", "apple", "itunes"]


# ── LLM routing via Ollama (llama3.2, runs locally, free) ─────────────────────

ROUTING_PROMPT = """You are a cross-border value routing agent. Rules:
- airtime: sending mobile credit to someone in a developing market (Africa, SE Asia, LatAm). A country must be mentioned.
- esim: traveler needs data for a trip or just landed somewhere.
- gift_card: buying a brand gift card (Steam, Netflix, Google Play) OR a gaming top-up (Mobile Legends, PUBG, Roblox, Fortnite, etc.) for the user themselves.

IMPORTANT: If the intent is buying a gaming top-up or gift card for the user themselves with NO recipient country mentioned, set country_code to "" and country_name to "International". Use the product name as the search_query exactly.

Return ONLY this JSON (no markdown, no explanation):
{"country_code":"NG","country_name":"Nigeria","product_type":"airtime","search_query":"MTN Nigeria","amount_usd":10,"reasoning":"MTN has 70% market share in Nigeria"}

Example for gaming top-up with no country:
{"country_code":"","country_name":"International","product_type":"gift_card","search_query":"Mobile Legends Diamonds International","amount_usd":0.18,"reasoning":"User wants Mobile Legends diamonds, no country specified, using international product"}

Intent: """

TEAM_PROMPT = """You are a cross-border value routing agent. Rules:
- airtime for developing markets (Africa, SE Asia, LatAm)
- esim for travelers / roaming
- gift_card for specific brands or US/EU recipients

Return ONLY a JSON array (no markdown, no explanation):
[{"name":"Alice","country_code":"NG","country_name":"Nigeria","product_type":"airtime","search_query":"MTN Nigeria","amount_usd":10,"reasoning":"MTN dominant in Nigeria"},{"name":"Bob","country_code":"PH","country_name":"Philippines","product_type":"airtime","search_query":"Globe Philippines","amount_usd":15,"reasoning":"Globe has 47% share in PH"}]

Intent: """


OLLAMA_URL = "http://localhost:11434/api/generate"


def _llm(prompt: str) -> str:
    r = requests.post(OLLAMA_URL, json={
        "model": "llama3.2",
        "prompt": prompt,
        "stream": False,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["response"].strip()


def _extract_json(text: str):
    text = re.sub(r"```(?:json)?", "", text).strip("`").strip()
    # Try the whole string first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find last valid JSON object or array
    for match in reversed(list(re.finditer(r"(\[[\s\S]*?\]|\{[\s\S]*?\})", text))):
        try:
            return json.loads(match.group(1))
        except Exception:
            continue
    raise ValueError(f"No valid JSON found in LLM response: {text[:200]}")


def detect_amount(text: str, default: float = 10.0):
    m = re.search(r"\$(\d+(?:\.\d+)?)", text) or re.search(r"(\d+(?:\.\d+)?)\s*dollar", text)
    return float(m.group(1)) if m else default


def _sanitize_plan(plan: dict, fallback_intent: str = "") -> dict:
    """Ensure required fields are clean ASCII strings."""
    cc = plan.get("country_code", "NG")
    cn = plan.get("country_name", "Nigeria")
    pt = plan.get("product_type", "airtime")
    if pt not in ("airtime", "esim", "gift_card"):
        pt = "gift_card" if cc == "" else "airtime"
    # Rebuild search_query if missing or contains non-ASCII
    sq = plan.get("search_query", "")
    if not sq or not sq.isascii():
        if pt == "airtime":
            sq = OPERATOR_MAP.get(cc, f"airtime {cn}")
        elif pt == "esim":
            sq = f"eSIM {cn}"
        else:
            # For gift cards with no country, use the raw intent as the query
            sq = fallback_intent if fallback_intent else f"gift card"
    amount = float(plan.get("amount_usd") or detect_amount(fallback_intent) or 10.0)
    # Extract phone number from intent if present (e.g. "+234 800 123 4567")
    phone = plan.get("phone_number") or ""
    if not phone:
        m = re.search(r"\+?\d[\d\s\-]{7,14}\d", fallback_intent)
        if m:
            phone = re.sub(r"[\s\-]", "", m.group())
    plan.update({"country_code": cc, "country_name": cn,
                 "product_type": pt, "search_query": sq,
                 "amount_usd": amount, "phone_number": phone})
    return plan


def parse_intent(intent: str) -> dict:
    print(" 🧠 Reasoning about destination and instrument...", flush=True)
    raw = _llm(ROUTING_PROMPT + intent)
    try:
        plan = _extract_json(raw)
        return _sanitize_plan(plan, intent)
    except Exception:
        print("   (LLM parse failed, falling back to keyword routing)")
        return _fallback_parse(intent)


def parse_team_intent(intent: str) -> list[dict]:
    print(" 🧠 Reasoning about recipients and instruments...", flush=True)
    raw = _llm(TEAM_PROMPT + intent)
    try:
        recipients = _extract_json(raw)
        if isinstance(recipients, dict):
            recipients = [recipients]
        for i, r in enumerate(recipients):
            if not r.get("name"):
                r["name"] = f"Recipient {i+1}"
            _sanitize_plan(r)
        return recipients
    except Exception:
        print("   (LLM parse failed, falling back to keyword routing)")
        return _fallback_team_parse(intent)


def _fallback_parse(intent: str) -> dict:
    text = intent.lower()
    country_code, country_name = "NG", "Nigeria"
    for keyword, (code, name) in COUNTRY_MAP.items():
        if keyword in text:
            country_code, country_name = code, name
            break
    product_type = "airtime"
    for ptype, keywords in PRODUCT_KEYWORDS.items():
        if any(k in text for k in keywords):
            product_type = ptype
            break
    amount = detect_amount(text)
    query = OPERATOR_MAP.get(country_code, f"airtime {country_name}") if product_type == "airtime" \
        else f"eSIM {country_name}" if product_type == "esim" \
        else f"gift card {country_name}"
    return {"country_code": country_code, "country_name": country_name,
            "product_type": product_type, "search_query": query,
            "amount_usd": amount, "reasoning": "keyword-based fallback"}


def _fallback_team_parse(intent: str) -> list[dict]:
    segments = re.split(r"[,|;]", intent)
    recipients = []
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue
        plan = _fallback_parse(seg)
        name_match = re.match(r"([A-Z][a-z]+)", seg)
        plan["name"] = name_match.group(1) if name_match else f"Recipient {i+1}"
        recipients.append(plan)
    return recipients


# ── Bitrefill API ──────────────────────────────────────────────────────────────

def get_balance():
    r = requests.get(f"{BASE}/accounts/balance", headers=HEADERS)
    r.raise_for_status()
    data = r.json()["data"]
    if data.get("currency") != "BTC":
        data["balance"] = round(data["balance"] / 100, 2)
    return data


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


def pkg_value(pkg: dict):
    """Return (api_value, comparable_usd) for a package.
    api_value      — the exact value to send to the invoice API (preserved as-is)
    comparable_usd — USD price used only for selecting the best match
    """
    raw = pkg.get("value", "")
    # Always compare by price (USD), never by value (may be local currency or descriptive text)
    comparable = float(pkg.get("price") or pkg.get("amount") or 0)
    # Preserve the original type for the API: numeric string → int, already-int → int, text → str
    try:
        api_value = int(float(raw))  # "5000" or 5000 → 5000
        # If the string had a decimal part, keep it as-is (e.g. "10.5" → 10 would be wrong)
        if str(api_value) != str(raw).rstrip('0').rstrip('.'):
            api_value = raw
    except (ValueError, TypeError):
        api_value = raw  # descriptive string, pass as-is
    return api_value, comparable


def best_denomination(products: list, amount_usd: float):
    best_product, best_value, best_diff = None, None, float("inf")
    for p in products[:3]:
        details = get_product(p["id"])
        for pkg in details.get("packages", []):
            v, comparable = pkg_value(pkg)
            if not comparable:
                continue
            diff = abs(comparable - amount_usd)
            if diff < best_diff:
                best_diff, best_product, best_value = diff, details, v
    return best_product, best_value


def create_invoice(products_payload: list, pay: bool = True, phone_number: str = None):
    """
    products_payload: list of {"product_id": str, "value": ..., "quantity": int}
    phone_number: required for airtime top-ups
    """
    body = {
        "products": products_payload,
        "payment_method": "balance",
        "auto_pay": pay,
    }
    if phone_number:
        body["phone_number"] = phone_number
    r = requests.post(f"{BASE}/invoices", headers=HEADERS, json=body)
    if r.status_code == 400:
        err = r.json()
        msg = err.get("message", "Bad request")
        if "phone_number" in msg.lower():
            raise ValueError("This product requires a recipient phone number. Please include it in your intent, e.g. '+234 800 000 0000'.")
        raise ValueError(f"Bitrefill API error: {msg}")
    r.raise_for_status()
    return r.json()["data"]


def pay_invoice(invoice_id: str):
    r = requests.post(f"{BASE}/invoices/{invoice_id}/pay", headers=HEADERS, json={"payment_method": "balance"})
    r.raise_for_status()
    return r.json()["data"]


def poll_invoice(invoice_id: str, timeout: int = 90):
    """Poll until ALL orders are delivered."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/invoices/{invoice_id}", headers=HEADERS)
        r.raise_for_status()
        data = r.json()["data"]
        orders = data.get("orders", [])
        if orders and all(o.get("status") == "delivered" for o in orders):
            return orders
        delivered = sum(1 for o in orders if o.get("status") == "delivered")
        print(f"   ⏳ {delivered}/{len(orders)} delivered...", flush=True)
        time.sleep(3)
    raise TimeoutError("Orders not delivered in time")


# ── Single-recipient run ───────────────────────────────────────────────────────

def run(intent: str, test_mode: bool = False):
    print(f"\n{'='*55}")
    print(f"  Value Router — Autonomous Cross-Border Agent")
    print(f"{'='*55}")
    print(f"\n Intent : {intent}")

    bal = get_balance()
    print(f" Balance : {bal['balance']} {bal['currency']}")

    plan = parse_intent(intent)
    print(f"\n Routing decision:")
    print(f"   Destination : {plan['country_name']} ({plan['country_code']})")
    print(f"   Instrument  : {plan['product_type']}")
    print(f"   Amount      : ${plan['amount_usd']}")
    print(f"   Search      : {plan['search_query']}")

    if test_mode:
        _run_test([(plan, "Recipient")])
        return

    if bal["balance"] <= 0:
        print("\n ⚠  Balance is 0. Use --test or top up your account.")
        return

    products = search_products(plan["search_query"], plan["country_code"]) or search_products(plan["search_query"])
    if not products:
        print(" ❌ No products found.")
        return

    product, value = best_denomination(products, plan["amount_usd"])
    if not product:
        print(" ❌ Could not match denomination.")
        return

    print(f"\n Selected: {product['name']} — ${value}")
    print(f" Creating invoice and paying from balance...")

    invoice = create_invoice([{"product_id": product["id"], "value": value, "quantity": 1}], pay=False)
    pay_invoice(invoice["id"])
    print(f" Invoice: {invoice['id']}")

    print(f" Polling for delivery...")
    orders = poll_invoice(invoice["id"])
    _print_results([(plan, orders[0])])


# ── Team (multi-recipient) run ─────────────────────────────────────────────────

def run_team(intent: str, test_mode: bool = False):
    print(f"\n{'='*55}")
    print(f"  Value Router — Team Basket Mode")
    print(f"{'='*55}")
    print(f"\n Intent : {intent}\n")

    bal = get_balance()
    print(f" Balance : {bal['balance']} {bal['currency']}\n")

    recipients = parse_team_intent(intent)
    if not recipients:
        print(" ❌ Could not parse any recipients.")
        return

    print(f" Routing {len(recipients)} recipients:\n")

    if test_mode:
        plans_with_names = [(r, r["name"]) for r in recipients]
        _run_test(plans_with_names, team=True)
        return

    if bal["balance"] <= 0:
        print(" ⚠  Balance is 0. Use --test or top up your account.")
        return

    # Resolve best product per recipient
    basket = []
    resolved = []
    for r in recipients:
        print(f"   {r['name']} → {r['country_name']} | {r['product_type']} | ${r['amount_usd']}")
        products = search_products(r["search_query"], r["country_code"]) or search_products(r["search_query"])
        if not products:
            print(f"     ⚠  No products found, skipping.")
            continue
        product, value = best_denomination(products, r["amount_usd"])
        if not product:
            print(f"     ⚠  No matching denomination, skipping.")
            continue
        print(f"     ✓ {product['name']} — ${value}")
        basket.append({"product_id": product["id"], "value": value, "quantity": 1})
        resolved.append((r, product))

    if not basket:
        print("\n ❌ No products resolved.")
        return

    total = sum(item["value"] for item in basket)
    print(f"\n Basket: {len(basket)} products | Total: ~${total:.2f}")
    print(f" Creating ONE invoice for all recipients...")

    invoice = create_invoice(basket, pay=False)
    pay_invoice(invoice["id"])
    print(f" Invoice: {invoice['id']}")

    print(f" Polling until all {len(basket)} orders delivered...")
    orders = poll_invoice(invoice["id"])

    print(f"\n {'='*48}")
    print(f"  TEAM BUNDLE DELIVERED — {len(orders)} recipients")
    print(f" {'='*48}")
    for i, (r, order) in enumerate(zip(resolved, orders)):
        redemption = order[1].get("redemption_info", {}) if isinstance(order, tuple) else order.get("redemption_info", {})
        order_data = order[1] if isinstance(order, tuple) else order
        print(f"\n  [{i+1}] {r[0]['name']} — {r[0]['country_name']}")
        print(f"       Product : {r[1]['name']}")
        print(f"       Code    : {order_data.get('redemption_info', {}).get('code', 'N/A')}")
    print(f"\n {'='*48}\n")


def _run_test(plans_with_names: list, team: bool = False):
    """
    Test mode: creates a real invoice for each recipient using test-gift-card-code.
    Shows full routing decisions + invoice. Delivery triggers on Lightning settlement.
    """
    product = get_product(TEST_PRODUCT_ID)
    value, _ = pkg_value(product["packages"][0])

    label = "team basket" if team else "single purchase"
    print(f"\n [TEST MODE] {label} — {len(plans_with_names)} recipient(s)\n")

    print(f" Agent routing decisions:")
    print(f" {'─'*46}")
    for plan, name in plans_with_names:
        n = name if isinstance(name, str) else plan.get("name", "?")
        p = plan if isinstance(plan, dict) else plan
        instrument = {
            "airtime":   "📱 Airtime top-up  — universally redeemable, no smartphone needed",
            "esim":      "📡 eSIM data plan  — activates on device, no SIM swap needed",
            "gift_card": "🎁 Local gift card — optimized for recipient's market",
        }.get(p["product_type"], p["product_type"])
        print(f"\n  {n}")
        print(f"    Destination : {p['country_name']} ({p['country_code']})")
        print(f"    Instrument  : {instrument}")
        print(f"    Product     : {p['search_query']}")
        print(f"    Amount      : ${p['amount_usd']}")
    print(f"\n {'─'*46}")

    basket = [{"product_id": TEST_PRODUCT_ID, "value": value, "quantity": 1}
              for _ in plans_with_names]

    print(f"\n Creating {'one' if len(basket) == 1 else 'one multi-product'} invoice "
          f"({len(basket)} item{'s' if len(basket) > 1 else ''})...")
    invoice = create_invoice(basket, pay=False)
    invoice_id = invoice["id"]
    payment = invoice.get("payment", {})

    print(f" Invoice ID : {invoice_id}")
    print(f" Items      : {len(basket)}")
    if payment.get("lightning_invoice"):
        print(f" Lightning  : {payment['lightning_invoice'][:72]}...")
    elif payment.get("uri"):
        print(f" Pay URI    : {payment['uri'][:72]}...")

    # Quick poll — delivers if already settled or balance available
    print(f"\n Polling for delivery (30s)...")
    deadline = time.time() + 30
    orders = []
    data = {}
    while time.time() < deadline:
        r = requests.get(f"{BASE}/invoices/{invoice_id}", headers=HEADERS)
        data = r.json()["data"]
        orders = data.get("orders", [])
        delivered = sum(1 for o in orders if o.get("status") == "delivered")
        if delivered == len(basket):
            break
        print(f"   ⏳ {delivered}/{len(basket)} delivered...", flush=True)
        time.sleep(3)

    delivered_orders = [o for o in orders if o.get("status") == "delivered"]

    if len(delivered_orders) == len(basket):
        print(f"\n {'='*50}")
        print(f"  {'TEAM BUNDLE' if team else 'ORDER'} DELIVERED — {len(delivered_orders)} recipient(s)")
        print(f" {'='*50}")
        for i, ((plan, name), order) in enumerate(zip(plans_with_names, delivered_orders)):
            n = name if isinstance(name, str) else plan.get("name", "?")
            p = plan if isinstance(plan, dict) else plan
            redemption = order.get("redemption_info", {})
            print(f"\n  [{i+1}] {n} — {p['country_name']}")
            print(f"       Code  : {redemption.get('code', 'N/A')}")
            if redemption.get("pin"):
                print(f"       PIN   : {redemption['pin']}")
            print(f"       Order : {order['id']}")
        print(f"\n {'='*50}\n")
    else:
        print(f"\n {'='*50}")
        print(f"  INVOICE CREATED — awaiting settlement")
        print(f" {'='*50}")
        print(f"\n  Invoice : {invoice_id}")
        print(f"  Items   : {len(basket)} product(s) routed across {len(plans_with_names)} recipient(s)")
        print(f"  Status  : pending payment")
        print(f"\n  To complete: pay the Lightning invoice above.")
        print(f"  The agent then polls orders[0].status until 'delivered'")
        print(f"  and returns each redemption code — no human in the loop.\n")
        print(f" {'='*50}\n")


def _print_results(pairs: list):
    print(f"\n {'='*48}")
    print(f"  DELIVERED!")
    print(f" {'='*48}")
    for plan, order in pairs:
        redemption = order.get("redemption_info", {})
        print(f"\n  {plan['country_name']}")
        print(f"   Code    : {redemption.get('code', 'N/A')}")
        if redemption.get("pin"):
            print(f"   PIN     : {redemption['pin']}")
        print(f"   Order   : {order['id']}")
    print(f"\n {'='*48}\n")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test = "--test" in sys.argv
    team = "--team" in sys.argv
    flags = {"--test", "--team"}
    args = [a for a in sys.argv[1:] if a not in flags]
    intent = " ".join(args) if args else (
        "Alice in Lagos $10, Bob in Manila $15, Carlos in Mexico City $10"
        if team else "Send $10 to my brother in Lagos"
    )

    if team:
        run_team(intent, test_mode=test)
    else:
        run(intent, test_mode=test)
