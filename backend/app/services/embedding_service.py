"""
Embedding Service — generates vector embeddings via Google Gemini API.

Uses text-embedding-004 with output_dimensionality=384 to match the pgvector column.
Graceful degradation: returns None if API is unavailable or unconfigured.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"


def _get_api_key() -> Optional[str]:
    key = os.getenv("GOOGLE_API_KEY")
    if not key or key.startswith("your_"):
        return None
    return key


async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Generate a 384-dim embedding for the given text via Gemini.
    Returns None if API is unavailable.
    """
    if not text or not text.strip():
        return None

    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_GEMINI_URL}?key={api_key}",
                json={
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": EMBEDDING_DIM,
                },
            )
        if response.status_code != 200:
            logger.warning("Gemini embedding API returned %d: %s", response.status_code, response.text[:200])
            return None

        result = response.json()
        values = result.get("embedding", {}).get("values")
        if values and len(values) == EMBEDDING_DIM:
            return values

        logger.warning("Unexpected Gemini response shape")
        return None

    except Exception as exc:
        logger.warning("Gemini embedding call failed: %s", exc)
        return None
