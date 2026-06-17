"""
Product search + price extraction module.
Uses DuckDuckGo (free, no API key) + Ollama LLM to find Amazon product prices.
"""

import re
import json
import requests as req
from ddgs import DDGS


OLLAMA_URL = "http://localhost:11434/api/generate"


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Search DuckDuckGo and return results."""
    try:
        results = DDGS().text(query + " site:amazon.com", max_results=max_results)
        if not results:
            results = DDGS().text(query + " amazon price", max_results=max_results)
        return results or []
    except Exception as e:
        return []


def extract_price_with_llm(query: str, search_results: list[dict]) -> dict:
    """
    Use local LLM to extract the best product match, price, and link
    from search results snippets.
    """
    snippets = "\n\n".join([
        f"Title: {r.get('title','')}\nURL: {r.get('href','')}\nSnippet: {r.get('body','')}"
        for r in search_results[:6]
    ])

    prompt = f"""You are a shopping agent. The user wants to buy: "{query}"

Here are web search results:
{snippets}

Find the best match on Amazon. Extract:
- product_name: specific product name
- price_usd: numeric price in USD (estimate if not exact, use typical Amazon price for this item)
- url: the Amazon product URL (use the most relevant amazon.com URL from results, or construct a search URL)
- reasoning: why this is the best/cheapest option

Return ONLY valid JSON:
{{"product_name":"Spigen Tempered Glass iPhone 14","price_usd":8.99,"url":"https://www.amazon.com/dp/...","reasoning":"Spigen is the most reviewed budget option for iPhone screen protectors"}}"""

    try:
        r = req.post(OLLAMA_URL, json={
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False,
        }, timeout=60)
        raw = r.json()["response"].strip()
        # Extract JSON
        match = re.search(r'\{[\s\S]*?\}', raw)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    # Fallback: return first Amazon result with estimated price
    amazon_results = [r for r in search_results if "amazon.com" in r.get("href", "")]
    if amazon_results:
        return {
            "product_name": amazon_results[0]["title"][:80],
            "price_usd": 10.0,
            "url": amazon_results[0]["href"],
            "reasoning": "Best Amazon result found for your query.",
        }

    return {
        "product_name": query,
        "price_usd": 10.0,
        "url": f"https://www.amazon.com/s?k={query.replace(' ', '+')}",
        "reasoning": "Could not find exact price. Estimated $10 Amazon gift card.",
    }


def find_product(query: str) -> dict:
    """Full pipeline: search → extract → return product info."""
    results = web_search(query)
    product = extract_price_with_llm(query, results)

    # Round up to nearest gift card denomination available on Bitrefill
    # Amazon gift cards come in $1 increments, so round up to next dollar
    import math
    price = product.get("price_usd", 10.0)
    product["gift_card_amount"] = max(math.ceil(price), 5)  # min $5
    product["raw_results"] = results[:3]  # keep top 3 for display

    return product
