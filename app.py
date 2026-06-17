#!/usr/bin/env python3
"""
Value Router — Flask web application.
Serves the UI and streams agent output via SSE.
"""

import os
import re
import sys
import time
import json
import queue
import threading
import requests as req
from flask import Flask, request, Response, jsonify, send_from_directory

# ── Import agent logic ─────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
import agent as core

app = Flask(__name__, static_folder=".", static_url_path="")


# ── SSE helpers ────────────────────────────────────────────────────────────────

def sse(data: dict):
    return f"data: {json.dumps(data)}\n\n"


def stream_agent(intent: str, team: bool, test_mode: bool):
    """Run agent in a thread, yield SSE events."""
    q = queue.Queue()

    def emit(msg_type: str, **kwargs):
        q.put({"type": msg_type, **kwargs})

    def worker():
        try:
            if team:
                _stream_team(intent, test_mode, emit)
            else:
                _stream_single(intent, test_mode, emit)
        except Exception as e:
            emit("error", message=str(e))
        finally:
            emit("done")

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            event = q.get(timeout=90)
            yield sse(event)
            if event["type"] == "done":
                break
        except queue.Empty:
            yield sse({"type": "error", "message": "Timeout"})
            break


def _stream_single(intent: str, test_mode: bool, emit):
    emit("log", message=f"Intent: {intent}")

    bal = core.get_balance()
    emit("balance", value=bal["balance"], currency=bal["currency"])

    emit("log", message="🧠 Reasoning about destination and instrument...")
    plan = core.parse_intent(intent)
    emit("plan", data=plan)

    if test_mode:
        _do_test_purchase([plan], ["Recipient"], emit, team=False)
        return

    if bal["balance"] <= 0:
        emit("error", message="Balance is 0. Use test mode or top up your account.")
        return

    products = core.search_products(plan["search_query"], plan["country_code"]) \
               or core.search_products(plan["search_query"])
    if not products:
        emit("error", message="No products found for this intent.")
        return

    product, value = core.best_denomination(products, plan["amount_usd"])
    if not product:
        emit("error", message="No matching denomination found.")
        return

    emit("selected", product=product["name"], value=value)
    emit("log", message="Creating invoice and paying from balance...")

    invoice = core.create_invoice(
        [{"product_id": product["id"], "value": value, "quantity": 1}], pay=False
    )
    core.pay_invoice(invoice["id"])
    emit("invoice", id=invoice["id"])

    emit("log", message="Polling for delivery...")
    orders = core.poll_invoice(invoice["id"])
    redemption = orders[0].get("redemption_info", {})
    emit("delivered", recipients=[{
        "name": plan["country_name"],
        "product": product["name"],
        "value": value,
        "code": redemption.get("code", "N/A"),
        "pin": redemption.get("pin"),
        "order_id": orders[0]["id"],
    }])


def _stream_team(intent: str, test_mode: bool, emit):
    emit("log", message=f"Team intent: {intent}")

    bal = core.get_balance()
    emit("balance", value=bal["balance"], currency=bal["currency"])

    emit("log", message="🧠 Reasoning about recipients and instruments...")
    recipients = core.parse_team_intent(intent)
    emit("team_plan", data=recipients)

    if test_mode:
        names = [r.get("name", f"Recipient {i+1}") for i, r in enumerate(recipients)]
        _do_test_purchase(recipients, names, emit, team=True)
        return

    if bal["balance"] <= 0:
        emit("error", message="Balance is 0. Use test mode or top up your account.")
        return

    basket = []
    resolved = []
    for r in recipients:
        emit("log", message=f"Searching for {r['name']} → {r['country_name']}...")
        products = core.search_products(r["search_query"], r["country_code"]) \
                   or core.search_products(r["search_query"])
        if not products:
            emit("log", message=f"⚠ No products for {r['name']}, skipping.")
            continue
        product, value = core.best_denomination(products, r["amount_usd"])
        if not product:
            continue
        emit("log", message=f"✓ {r['name']} → {product['name']} ${value}")
        basket.append({"product_id": product["id"], "value": value, "quantity": 1})
        resolved.append((r, product, value))

    if not basket:
        emit("error", message="No products resolved for any recipient.")
        return

    emit("log", message=f"Creating one invoice for {len(basket)} recipients...")
    invoice = core.create_invoice(basket, pay=False)
    core.pay_invoice(invoice["id"])
    emit("invoice", id=invoice["id"])

    emit("log", message="Polling for all deliveries...")
    orders = core.poll_invoice(invoice["id"])

    result = []
    for (r, product, value), order in zip(resolved, orders):
        redemption = order.get("redemption_info", {})
        result.append({
            "name": r["name"],
            "country": r["country_name"],
            "product": product["name"],
            "value": value,
            "code": redemption.get("code", "N/A"),
            "pin": redemption.get("pin"),
            "order_id": order["id"],
        })
    emit("delivered", recipients=result)


def _do_test_purchase(plans, names, emit, team: bool):
    product = core.get_product(core.TEST_PRODUCT_ID)
    value = float(product["packages"][0]["value"])

    basket = [{"product_id": core.TEST_PRODUCT_ID, "value": value, "quantity": 1}
              for _ in plans]

    label = f"{len(basket)} item{'s' if len(basket) > 1 else ''}"
    emit("log", message=f"[TEST] Creating invoice — {label}...")
    invoice = core.create_invoice(basket, pay=False)
    invoice_id = invoice["id"]
    emit("invoice", id=invoice_id)

    emit("log", message="Polling for delivery (30s)...")
    deadline = time.time() + 30
    orders = []
    data = {}
    while time.time() < deadline:
        r = req.get(f"{core.BASE}/invoices/{invoice_id}", headers=core.HEADERS)
        data = r.json()["data"]
        orders = data.get("orders", [])
        delivered = sum(1 for o in orders if o.get("status") == "delivered")
        if delivered == len(basket):
            break
        emit("progress", delivered=delivered, total=len(basket))
        time.sleep(3)

    delivered_orders = [o for o in orders if o.get("status") == "delivered"]
    result = []
    for plan, name, order in zip(plans, names, delivered_orders if delivered_orders else [{}] * len(plans)):
        redemption = order.get("redemption_info", {}) if order else {}
        result.append({
            "name": name,
            "country": plan.get("country_name", ""),
            "product": plan.get("search_query", core.TEST_PRODUCT_ID),
            "value": plan.get("amount_usd", value),
            "reasoning": plan.get("reasoning", ""),
            "code": redemption.get("code", "pending"),
            "pin": redemption.get("pin"),
            "order_id": order.get("id", invoice_id) if order else invoice_id,
            "instrument": plan.get("product_type", "airtime"),
        })

    if delivered_orders:
        emit("delivered", recipients=result)
    else:
        emit("pending", invoice_id=invoice_id, recipients=result,
             payment=data.get("payment", {}))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/demo")
def demo():
    return send_from_directory(".", "app.html")

@app.route("/api/run")
def api_run():
    intent = request.args.get("intent", "")
    team = request.args.get("team", "false").lower() == "true"
    test = request.args.get("test", "true").lower() == "true"
    if not intent:
        return jsonify({"error": "intent required"}), 400
    return Response(
        stream_agent(intent, team, test),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.route("/api/balance")
def api_balance():
    bal = core.get_balance()
    return jsonify(bal)


if __name__ == "__main__":
    app.run(debug=False, port=5050, threaded=True)
