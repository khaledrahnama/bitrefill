# Value Router

**Autonomous cross-border value delivery agent built for the Bitrefill Hackathon 2025.**

Give it a plain-English intent. It picks the right instrument — airtime, gift card, or eSIM — for the destination country, then purchases it autonomously from your Bitrefill balance. No forms. No human clicks.

🎥 **[Watch the demo](https://youtu.be/YOUR_DEMO_LINK)**  
🌐 **[Landing page](https://khaledrahnama.github.io/value-router)**

---

## Examples

```bash
python agent.py "Send $10 to my brother in Lagos"
python agent.py "I just landed in Bangkok, get me eSIM data"
python agent.py "Top up $20 for my sister in Manila"
python agent.py "Buy a $25 Steam gift card"
```

## How it works

1. **Parse intent** — extracts destination country, product type, and amount from plain English
2. **Route** — selects the optimal instrument for the country (airtime > gift card > eSIM) across 170+ countries
3. **Purchase autonomously** — creates a Bitrefill invoice, pays from balance, polls `orders[0].status` until `delivered`, returns the redemption code

## Setup

### Requirements

- Python 3.10+
- A free Bitrefill API key → [bitrefill.com/account/developers](https://bitrefill.com/account/developers)

### Install

```bash
git clone https://github.com/khaledrahnama/bitrefill
cd value-router
pip install requests
```

### Run

```bash
export BITREFILL_API_KEY="your_key_here"

# Real purchase (requires balance)
python agent.py "Send $10 to my friend in Nigeria"

# Test mode — no real spend, auto-delivers
python agent.py "Send $10 to my friend in Nigeria" --test
```

## Tech stack

- **Bitrefill REST API v2** — products, invoices, orders, balance
- **Bitrefill MCP** — `https://api.bitrefill.com/mcp/<YOUR_KEY>`
- **Python 3** — no frameworks, minimal dependencies
- **170+ countries** — airtime, gift cards, eSIM data, bill payments
- **Lightning / crypto settlement**

## Bitrefill API endpoints used

| Endpoint | Purpose |
|---|---|
| `GET /accounts/balance` | Check spend capacity before purchase |
| `GET /products/search?q=` | Find the right product for the intent |
| `GET /products/{id}` | Get denominations and pricing |
| `POST /invoices` | Create the purchase invoice |
| `POST /invoices/{id}/pay` | Pay from account balance |
| `GET /invoices/{id}` | Poll `orders[0].status` for delivery |

## License

MIT
