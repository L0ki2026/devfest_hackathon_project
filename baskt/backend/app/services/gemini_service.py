"""Gemini multimodal + structured JSON (google-genai SDK)."""

from __future__ import annotations

import asyncio
import base64
import json

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import get_settings

IDENTIFY_PROMPT = (
    "List each distinct food or grocery item visible. Use simple searchable names "
    'such as "red bell pepper" or "plain greek yogurt". Ignore non-food objects.'
)

WORKOUT_PROMPT_TEMPLATE = (
    'Workout description: "{text}". Pantry: {pantry}. Return the workout kind '
    "(strength, endurance, or light), minutes (0 if not stated), and 2-3 whole-food "
    "suggestions each for before and after the workout. Prefer pantry items. Use short "
    "food names. General guidance only."
)


class IdentifyItems(BaseModel):
    items: list[dict] = Field(default_factory=list)


class WorkoutSuggestion(BaseModel):
    kind: str
    min: int = 0
    pre: list[str] = Field(default_factory=list)
    post: list[str] = Field(default_factory=list)


def _client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


async def identify_foods_from_image(image_b64: str, mime: str) -> list[str]:
    settings = get_settings()
    raw = base64.b64decode(image_b64)
    schema = types.Schema(
        type=types.Type.OBJECT,
        required=["items"],
        properties={
            "items": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["name"],
                    properties={"name": types.Schema(type=types.Type.STRING)},
                ),
            )
        },
    )

    def _call() -> list[str]:
        client = _client()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=raw, mime_type=mime or "image/jpeg"),
                        types.Part.from_text(text=IDENTIFY_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
            ),
        )
        text = response.text or "{}"
        data = json.loads(text)
        return [str(x.get("name", "")).strip() for x in data.get("items", []) if x.get("name")]

    return await asyncio.to_thread(_call)


async def suggest_workout_meals(text: str, pantry: list[str]) -> dict:
    settings = get_settings()
    pantry_str = ", ".join(pantry) if pantry else "none"
    prompt = WORKOUT_PROMPT_TEMPLATE.format(text=text, pantry=pantry_str)

    schema = types.Schema(
        type=types.Type.OBJECT,
        required=["kind", "min", "pre", "post"],
        properties={
            "kind": types.Schema(type=types.Type.STRING),
            "min": types.Schema(type=types.Type.INTEGER),
            "pre": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
            "post": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        },
    )

    def _call() -> dict:
        client = _client()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.3,
            ),
        )
        data = json.loads(response.text or "{}")
        return WorkoutSuggestion(
            kind=str(data.get("kind", "light")),
            min=int(data.get("min") or 0),
            pre=list(data.get("pre") or [])[:3],
            post=list(data.get("post") or [])[:3],
        ).model_dump()

    return await asyncio.to_thread(_call)


PARSE_GROCERY_PROMPT = (
    "Extract grocery foods visible in this image. Return each food with name, quantity "
    "(null if unknown), unit (g, piece, cup, l, etc.), and estimated=true when guessing. "
    "Ignore prices, tax, totals, and non-food items. Do not invent foods not visible."
)


async def parse_groceries_from_image(image_b64: str, mime: str) -> dict:
    settings = get_settings()
    raw = base64.b64decode(image_b64)
    schema = types.Schema(
        type=types.Type.OBJECT,
        required=["items", "needs_confirmation"],
        properties={
            "items": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["name"],
                    properties={
                        "name": types.Schema(type=types.Type.STRING),
                        "quantity": types.Schema(type=types.Type.NUMBER, nullable=True),
                        "unit": types.Schema(type=types.Type.STRING, nullable=True),
                        "estimated": types.Schema(type=types.Type.BOOLEAN),
                    },
                ),
            ),
            "needs_confirmation": types.Schema(type=types.Type.BOOLEAN),
            "warnings": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            ),
        },
    )

    def _call() -> dict:
        client = _client()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=raw, mime_type=mime or "image/jpeg"),
                        types.Part.from_text(text=PARSE_GROCERY_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
            ),
        )
        data = json.loads(response.text or "{}")
        items = []
        for i, row in enumerate(data.get("items") or []):
            if not row.get("name"):
                continue
            items.append(
                {
                    "name": str(row["name"]).strip(),
                    "quantity": row.get("quantity"),
                    "unit": row.get("unit") or "g",
                    "estimated": bool(row.get("estimated", True)),
                    "id": f"scan_{i + 1}",
                }
            )
        warnings = list(data.get("warnings") or [])
        if data.get("needs_confirmation", True):
            warnings.append("Confirm scanned items and quantities before relying on nutrients.")
        return {
            "items": items,
            "needs_confirmation": bool(data.get("needs_confirmation", True)),
            "warnings": warnings,
            "source": "gemini",
        }

    return await asyncio.to_thread(_call)