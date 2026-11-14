"""Open Food Facts search (packaged foods, per 100 g)."""

from __future__ import annotations

import httpx


def _r1(n: float | None) -> float:
    return round((float(n or 0)) * 10) / 10


def _tannin_tag(name: str) -> str:
    import re

    return "tannin" if re.search(r"coffee|\btea\b|cocoa|chocolate", name, re.I) else ""


async def search_open_food_facts(query: str, page_size: int = 5) -> list[dict]:
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": page_size,
        "fields": "code,product_name,brands,ingredients_text,nutriments",
    }
    headers = {"User-Agent": "baskt/1.0 (student project)"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.RequestError:
        return []
    if resp.status_code != 200:
        return []

    products = (resp.json() or {}).get("products") or []
    out: list[dict] = []
    for x in products:
        if not x.get("product_name"):
            continue
        n = x.get("nutriments") or {}
        brands = x.get("brands") or ""
        brand_bit = f" ({brands.split(',')[0]})" if brands else ""
        name = x["product_name"] + brand_bit
        out.append(
            {
                "id": "o" + str(x.get("code", "")),
                "name": name,
                "srv": "100 g",
                "kcal": _r1(n.get("energy-kcal_100g")),
                "p": _r1(n.get("proteins_100g")),
                "c": _r1(n.get("carbohydrates_100g")),
                "f": _r1(n.get("fat_100g")),
                "fib": _r1(n.get("fiber_100g")),
                "fe": _r1((n.get("iron_100g") or 0) * 1000),
                "vc": _r1((n.get("vitamin-c_100g") or 0) * 1000),
                "ca": _r1((n.get("calcium_100g") or 0) * 1000),
                "ing": x.get("ingredients_text") or "",
                "tag": _tannin_tag(name),
                "src": "Open Food Facts",
            }
        )
    return out