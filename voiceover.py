#!/usr/bin/env python3
"""
Generate voiceover audio for the Value Router demo video.
Outputs one audio file per segment so you can sync with screen recording.
Run: python3 voiceover.py
"""

import subprocess
import os

VOICE = "Samantha"
RATE = 185  # words per minute — natural and clear
OUT_DIR = os.path.join(os.path.dirname(__file__), "voiceover")
os.makedirs(OUT_DIR, exist_ok=True)

SEGMENTS = [
    # (filename, text)
    ("00_intro", """
        Value Router.
        Three words that shouldn't go together: buy anything, pay with crypto, no clicks.
        Let me show you what that actually means.
    """),

    ("01_problem", """
        Right now, if you want to send value to someone in Lagos,
        or get data for a trip to Bangkok, or reward your team across five countries —
        you have to make decisions. What product? Which operator? Which amount?
        And then you have to execute. Multiple steps. Multiple platforms.
        Value Router removes all of that.
    """),

    ("02_landing", """
        This is the landing page.
        Clean. One idea. You describe what you need — the agent does the rest.
        Let me open the app.
    """),

    ("03_app_open", """
        The app has two modes. Value Router on the left — for sending value cross-border.
        And Shop and Pay — for buying anything on Amazon with crypto.
        Let me start with Value Router.
    """),

    ("04_single_intent", """
        I type: send ten dollars to my brother in Lagos.
        I hit Run Agent.
        Watch what happens — the agent is not looking this up in a table.
        It's reasoning. It knows MTN has seventy percent market share in Nigeria.
        It knows airtime works on any handset, no internet needed.
        That's the right call.
    """),

    ("05_single_result", """
        Routing decision locked in — Nigeria, airtime, MTN.
        Invoice created on Bitrefill. Paid from balance.
        Polling for delivery.
        And done — redemption code returned. No human clicked pay. Not once.
    """),

    ("06_team_intro", """
        Now watch this. Team basket mode.
        One intent — three people, three countries, three different currencies.
        Alice in Lagos, Bob in Manila, Carlos in Mexico City.
    """),

    ("07_team_reasoning", """
        The agent reasons about each person independently.
        MTN Nigeria for Alice. Globe Philippines for Bob. Telcel Mexico for Carlos.
        Three routing decisions. One invoice. One payment.
        This is the multi-product order feature of Bitrefill's API —
        we're using it to do something genuinely new.
    """),

    ("08_team_result", """
        Single invoice. Three products. Settled in one go.
        That's not a UX shortcut — that's the API doing real work.
    """),

    ("09_shop_intro", """
        Now the feature I'm most proud of. Shop and Pay.
        What if you don't know which Bitrefill product you need?
        You just know what you want to buy.
        I type: cheapest screen protector for iPhone fourteen on Amazon.
    """),

    ("10_shop_search", """
        The agent searches the web in real time.
        No API key. No paid service. Just DuckDuckGo and a local LLM.
        It finds the best match, extracts the price,
        and returns a direct Amazon link.
    """),

    ("11_shop_result", """
        Spigen Tempered Glass — eight dollars and ninety-nine cents.
        Here's the Amazon link. You can verify it right now.
        The agent is telling me: I'll buy a nine-dollar Amazon gift card from Bitrefill.
        You use the code on Amazon to pay.
        I hit confirm.
    """),

    ("12_shop_purchase", """
        Invoice created. Paid autonomously. Polling.
        And there it is — Amazon gift card, delivered, code ready to use.
        From a plain English sentence to a redeemable code.
        No forms. No decisions. No clicks.
    """),

    ("13_innovation", """
        Three things make this different from a wrapper around the Bitrefill API.
        First — the agent decides. A local LLM reasons about every destination.
        Second — multi-product orders. One invoice, many recipients, real API usage.
        Third — the Shop and Pay bridge. Web search plus autonomous settlement
        is a combination nobody else is doing here.
    """),

    ("14_close", """
        Value Router. Runs locally. Free LLM. No subscriptions.
        Connects to Bitrefill over MCP and REST.
        Code is on GitHub. The app is live right now.
        You describe the intent. The agent handles the rest.
        That's the whole idea.
    """),
]


def generate(filename, text):
    # Clean up whitespace
    text = " ".join(text.split())
    path = os.path.join(OUT_DIR, f"{filename}.aiff")
    print(f"  Generating {filename}...")
    subprocess.run([
        "say",
        "-v", VOICE,
        "-r", str(RATE),
        "-o", path,
        text,
    ], check=True)
    print(f"  Saved: {path}")
    return path


if __name__ == "__main__":
    print(f"\nGenerating {len(SEGMENTS)} voiceover segments...\n")
    paths = []
    for name, text in SEGMENTS:
        p = generate(name, text)
        paths.append(p)

    # Also generate one combined file
    print("\nCombining into full voiceover...")
    combined = os.path.join(OUT_DIR, "FULL_VOICEOVER.aiff")
    # Use sox if available, otherwise just list the files
    result = subprocess.run(["which", "sox"], capture_output=True)
    if result.returncode == 0:
        subprocess.run(["sox"] + paths + [combined], check=True)
        print(f"  Full file: {combined}")
    else:
        print("  (Install sox to merge: brew install sox)")
        print("  Individual segments saved to ./voiceover/")

    print(f"\nDone. {len(paths)} segments in ./voiceover/\n")
    print("MOUSE CUE GUIDE:")
    print("────────────────────────────────────────────────")
    cues = [
        ("00_intro",        "Show landing page hero text"),
        ("01_problem",      "Stay on landing page"),
        ("02_landing",      "Scroll landing page slowly"),
        ("03_app_open",     "Click Launch → open /demo, show both tabs"),
        ("04_single_intent","Click 'Lagos' example pill, click Run Agent"),
        ("05_single_result","Watch routing card appear, scroll to invoice"),
        ("06_team_intro",   "Click Team Basket tab, click Alice/Bob/Carlos example"),
        ("07_team_reasoning","Click Run Agent, watch 3 routing decisions"),
        ("08_team_result",  "Show invoice ID, scroll to show '3 items'"),
        ("09_shop_intro",   "Click Shop & Pay tab"),
        ("10_shop_search",  "Type in search box, click Search & Find Price"),
        ("11_shop_result",  "Point to product name, price, Amazon link"),
        ("12_shop_purchase","Click Confirm & Buy, watch gift card code appear"),
        ("13_innovation",   "Switch between tabs to show the 3 features"),
        ("14_close",        "Show GitHub repo, then back to app running"),
    ]
    for name, cue in cues:
        print(f"  [{name}]  →  {cue}")
    print("────────────────────────────────────────────────\n")
