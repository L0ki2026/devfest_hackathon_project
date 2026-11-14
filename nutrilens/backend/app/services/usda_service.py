"""USDA FoodData Central client with demo fallback and in-memory cache."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.schemas import Nutrients
from app.services.matching import FoodCandidate, normalize_name, score_match
from app.services.nutrition import dict_to_nutrients

# USDA nutrient numbers (FoodData Central)
USDA_NUTRIENT_IDS = {
    1008: "calories_kcal",
    1003: "protein_g",
    1005: "carbs_g",
    1004: "fat_g",
    1079: "fiber_g",
    1087: "calcium_mg",
    1089: "iron_mg",
    1092: "potassium_mg",
    1162: "vitamin_c_mg",
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEMO_FOODS_PATH = DATA_DIR / "demo_foods.json"
CACHE_DB_PATH = DATA_DIR / "usda_cache.sqlite"


class UsdaServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UsdaService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._demo_foods: list[dict[str, Any]] | None = None
        self._search_cache: dict[str, list[dict]] = {}
        self._detail_cache: dict[int, dict] = {}
        self._init_cache_db()

    def _init_cache_db(self) -> None:
        CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fdc_detail (
                    fdc_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _load_demo_foods(self) -> list[dict[str, Any]]:
        if self._demo_foods is None:
            with open(DEMO_FOODS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self._demo_foods = data["foods"]
        return self._demo_foods

    def use_demo(self) -> bool:
        return self.settings.demo_mode or not self.settings.usda_configured()

    @property
    def data_source(self) -> str:
        return "demo" if self.use_demo() else "usda"

    async def search_foods(self, query: str, page_size: int = 10) -> list[dict[str, Any]]:
        key = normalize_name(query)
        if key in self._search_cache:
            return self._search_cache[key]

        if self.use_demo():
            results = self._demo_search(query, page_size)
            self._search_cache[key] = results
            return results

        url = f"{self.settings.usda_base_url}/foods/search"
        params = {
            "api_key": self.settings.fdc_api_key,
            "query": query,
            "pageSize": page_size,
            "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.usda_timeout_seconds) as client:
                resp = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise UsdaServiceError("usda_timeout", "USDA API request timed out.") from exc
        except httpx.RequestError as exc:
            raise UsdaServiceError("usda_network", f"USDA API network error: {exc}") from exc

        if resp.status_code == 429:
            raise UsdaServiceError("usda_rate_limit", "USDA API rate limit exceeded.")
        if resp.status_code in (401, 403):
            raise UsdaServiceError("usda_auth", "USDA API authentication failed.")
        if resp.status_code >= 500:
            raise UsdaServiceError("usda_upstream", "USDA API is unavailable.")
        if resp.status_code != 200:
            raise UsdaServiceError(
                "usda_error",
                f"USDA search failed with status {resp.status_code}.",
            )

        body = resp.json()
        foods = body.get("foods") or []
        self._search_cache[key] = foods
        self._persist_search_cache(key, foods)
        return foods

    def _demo_search(self, query: str, page_size: int) -> list[dict[str, Any]]:
        q = normalize_name(query)
        foods = self._load_demo_foods()
        hits: list[dict[str, Any]] = []
        for food in foods:
            keys = [normalize_name(k) for k in food.get("search_keys", [])]
            desc = normalize_name(food["description"])
            if any(k in q or q in k for k in keys) or q in desc:
                hits.append(
                    {
                        "fdcId": food["fdc_id"],
                        "description": food["description"],
                        "dataType": food.get("data_type", "Demo"),
                    }
                )
            elif any(t in desc for t in q.split()):
                hits.append(
                    {
                        "fdcId": food["fdc_id"],
                        "description": food["description"],
                        "dataType": food.get("data_type", "Demo"),
                    }
                )
        return hits[:page_size]

    async def get_food_detail(self, fdc_id: int) -> dict[str, Any]:
        if fdc_id in self._detail_cache:
            return self._detail_cache[fdc_id]

        cached = self._read_fdc_cache(fdc_id)
        if cached:
            self._detail_cache[fdc_id] = cached
            return cached

        if self.use_demo() or fdc_id >= 900000:
            detail = self._demo_detail(fdc_id)
            if detail:
                self._detail_cache[fdc_id] = detail
                return detail
            raise UsdaServiceError("demo_not_found", f"Demo food fdc_id={fdc_id} not found.", 404)

        url = f"{self.settings.usda_base_url}/food/{fdc_id}"
        params = {"api_key": self.settings.fdc_api_key}
        try:
            async with httpx.AsyncClient(timeout=self.settings.usda_timeout_seconds) as client:
                resp = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise UsdaServiceError("usda_timeout", "USDA API request timed out.") from exc
        except httpx.RequestError as exc:
            raise UsdaServiceError("usda_network", f"USDA API network error: {exc}") from exc

        if resp.status_code == 429:
            raise UsdaServiceError("usda_rate_limit", "USDA API rate limit exceeded.")
        if resp.status_code in (401, 403):
            raise UsdaServiceError("usda_auth", "USDA API authentication failed.")
        if resp.status_code == 404:
            raise UsdaServiceError("usda_not_found", f"Food fdc_id={fdc_id} not found.", 404)
        if resp.status_code >= 500:
            raise UsdaServiceError("usda_upstream", "USDA API is unavailable.")
        if resp.status_code != 200:
            raise UsdaServiceError("usda_error", f"USDA detail failed with status {resp.status_code}.")

        detail = resp.json()
        self._detail_cache[fdc_id] = detail
        self._persist_fdc_cache(fdc_id, detail)
        return detail

    def _demo_detail(self, fdc_id: int) -> dict[str, Any] | None:
        for food in self._load_demo_foods():
            if food["fdc_id"] == fdc_id:
                return {
                    "fdcId": fdc_id,
                    "description": food["description"],
                    "dataType": food.get("data_type", "Demo"),
                    "demo_nutrients_per_100g": food["nutrients_per_100g"],
                    "default_grams_per_piece": food.get("default_grams_per_piece"),
                }
        return None

    def nutrients_from_detail(self, detail: dict[str, Any]) -> Nutrients:
        if "demo_nutrients_per_100g" in detail:
            return dict_to_nutrients(detail["demo_nutrients_per_100g"])

        raw: dict[str, float | None] = {v: None for v in USDA_NUTRIENT_IDS.values()}
        for item in detail.get("foodNutrients") or []:
            nutrient = item.get("nutrient") or {}
            nid = nutrient.get("id") or item.get("nutrientId")
            if nid not in USDA_NUTRIENT_IDS:
                continue
            field = USDA_NUTRIENT_IDS[nid]
            amount = item.get("amount")
            if amount is None:
                continue
            unit = (nutrient.get("unitName") or "").upper()
            if field == "calories_kcal" and unit == "KJ":
                amount = amount / 4.184
            raw[field] = float(amount)
        return Nutrients(**raw)

    def default_grams_per_piece(self, detail: dict[str, Any]) -> float | None:
        gpp = detail.get("default_grams_per_piece")
        if gpp is not None:
            return float(gpp)
        return None

    def build_candidates(self, query: str, search_results: list[dict]) -> list[FoodCandidate]:
        out: list[FoodCandidate] = []
        for row in search_results:
            fdc_id = row.get("fdcId")
            desc = row.get("description") or ""
            data_type = row.get("dataType") or ""
            if fdc_id is None:
                continue
            sc = score_match(query, desc, data_type)
            out.append(FoodCandidate(fdc_id=int(fdc_id), description=desc, data_type=data_type, score=sc))
        return out

    def _persist_fdc_cache(self, fdc_id: int, payload: dict) -> None:
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO fdc_detail (fdc_id, payload) VALUES (?, ?)",
                (fdc_id, json.dumps(payload)),
            )
            conn.commit()
        finally:
            conn.close()

    def _read_fdc_cache(self, fdc_id: int) -> dict | None:
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            row = conn.execute(
                "SELECT payload FROM fdc_detail WHERE fdc_id = ?", (fdc_id,)
            ).fetchone()
            if row:
                return json.loads(row[0])
        finally:
            conn.close()
        return None

    def _persist_search_cache(self, query: str, payload: list) -> None:
        conn = sqlite3.connect(CACHE_DB_PATH)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache (query, payload) VALUES (?, ?)",
                (query, json.dumps(payload)),
            )
            conn.commit()
        finally:
            conn.close()


_usda: UsdaService | None = None


def get_usda_service() -> UsdaService:
    global _usda
    if _usda is None:
        _usda = UsdaService()
    return _usda