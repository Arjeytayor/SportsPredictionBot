"""NVIDIA NIM integration for SportsPredictionBot.

Two roles:
  1. ENRICH  — extract structured signals from raw text (news, injury reports)
  2. EXPLAIN — generate plain-English narratives from model predictions

Uses NVIDIA's OpenAI-compatible chat completions endpoint.
"""

import json
import time
from typing import Dict, List, Optional

import requests

from config import NIM_API_KEY
from logger import logger

# ── NIM endpoint ────────────────────────────────────────────────────────────
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Model IDs (all free-tier eligible)
NIM_ENRICHER = "mistralai/mistral-large-3-675b-instruct-2512"
NIM_EXPLAINER = "qwen/qwen3.5-122b-a10b"
NIM_FALLBACK = "deepseek-ai/deepseek-v4-flash"

# ── System prompts ────────────────────────────────────────────────────────
ENRICHMENT_SYSTEM = (
    "You are a sports data analyst. Given match context, extract exactly the "
    "following signals as a JSON object and NOTHING else. Return only valid JSON, "
    "no markdown, no explanation.\n\n"
    "Schema:\n"
    '{"home_sentiment": float, "away_sentiment": float, '
    '"home_injury_flag": int, "away_injury_flag": int, '
    '"home_form_signal": float, "away_form_signal": float, '
    '"rivalry_index": float, "weather_penalty": float}'
)

EXPLANATION_SYSTEM = (
    "You are a sports analyst for 'The African Investor' sports channel. "
    "Given prediction data, write exactly ONE concise sentence explaining WHY "
    "the model favours this outcome. Be specific. No bullet points, no markdown. "
    "Write in a confident, pundit-style tone. Maximum 150 characters."
)


# ── Core NIM wrapper ──────────────────────────────────────────────────────
def call_nim(
    prompt: str,
    system: str = "",
    model: str = NIM_ENRICHER,
    max_tokens: int = 256,
    retries: int = 3,
) -> Optional[str]:
    """Call a NIM model. Returns text or None on failure."""
    if not NIM_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {NIM_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }

    for attempt in range(retries):
        try:
            resp = requests.post(NIM_BASE_URL, headers=headers, json=payload, timeout=30)

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"NIM rate limit on {model}. Waiting {wait}s...")
                time.sleep(wait)
                if attempt == retries - 1 and model != NIM_FALLBACK:
                    logger.info(f"Switching NIM to fallback: {NIM_FALLBACK}")
                    payload["model"] = NIM_FALLBACK
                continue

            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        except requests.RequestException as exc:
            logger.warning(f"NIM request failed (attempt {attempt + 1}): {exc}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return None


# ── ENRICH: text → structured features ────────────────────────────────────
def extract_nim_features(
    home_team: str,
    away_team: str,
    text_snippets: List[str],
) -> Dict[str, float]:
    """Send raw text to NIM, get back numeric features."""
    default_features = {
        "home_sentiment": 0.0, "away_sentiment": 0.0,
        "home_injury_flag": 0, "away_injury_flag": 0,
        "home_form_signal": 0.0, "away_form_signal": 0.0,
        "rivalry_index": 0.0, "weather_penalty": 0.0,
    }

    if not text_snippets:
        return default_features

    combined_text = "\n\n---\n\n".join(text_snippets[:5])
    prompt = (
        f"Match: {home_team} (home) vs {away_team} (away)\n\n"
        f"Context articles:\n{combined_text}\n\n"
        "Extract the JSON feature object."
    )

    raw = call_nim(prompt, system=ENRICHMENT_SYSTEM, model=NIM_ENRICHER, max_tokens=256)
    if not raw:
        return default_features

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```", 2)[-1].strip()
    try:
        features = json.loads(raw)
        for key in default_features:
            val = features.get(key, default_features[key])
            default_features[key] = int(val) if isinstance(default_features[key], int) else float(val)
        return default_features
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"NIM feature parse failed: {exc}")
        return default_features


# ── EXPLAIN: prediction → narrative ───────────────────────────────────────
def generate_nim_explanation(
    home_team: str,
    away_team: str,
    pick_type: str,
    confidence: float,
    home_win_prob: float,
    draw_prob: float,
    away_win_prob: float,
    model_source: str = "",
) -> Optional[str]:
    """Generate a one-sentence NIM narrative explaining the pick."""
    if not NIM_API_KEY:
        return None

    prompt = (
        f"Match: {home_team} vs {away_team}\n"
        f"Model: {model_source}\n"
        f"Pick: {pick_type} (confidence {confidence:.1f}%)\n"
        f"Probabilities: Home {home_win_prob*100:.1f}%, "
        f"Draw {draw_prob*100:.1f}%, Away {away_win_prob*100:.1f}%\n\n"
        "Explain why this pick makes sense in one sentence."
    )

    return call_nim(
        prompt,
        system=EXPLANATION_SYSTEM,
        model=NIM_EXPLAINER,
        max_tokens=150,
    )
