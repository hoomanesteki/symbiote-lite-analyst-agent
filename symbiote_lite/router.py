from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, Optional

from .dates import DATASET_YEAR

ROUTER_SYSTEM_PROMPT = f"""
You are a routing assistant for an NYC Yellow Taxi dataset (YEAR {DATASET_YEAR} only).
Output JSON ONLY:
- intent: one of [\"trip_frequency\",\"vendor_inactivity\",\"fare_trend\",\"tip_trend\",\"sample_rows\",\"unknown\"]
- dataset_match: true/false
Return JSON only.
""".strip()

REWRITE_SYSTEM_PROMPT = """
You rewrite user messages into a clear, analyst-friendly NYC taxi question for YEAR 2022.
Output JSON ONLY:
{\"rewritten\": \"string\", \"intent_hint\": \"...\", \"granularity_hint\": \"...\", \"metric_hint\": \"...\"}
Return JSON only.
""".strip()

def _openai_client() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None

def _openai_model_name() -> str:
    return os.getenv("SYMBIOTE_MODEL", "gpt-4")

class _OpenAIModelShim:
    def __init__(self, client: Any):
        self._client = client

    class _Resp:
        def __init__(self, text: str):
            self.text = text

    def generate_content(self, prompt: str) -> Any:
        try:
            resp = self._client.responses.create(
                model=_openai_model_name(),
                reasoning={"effort": "low"},
                temperature=0,
                input=prompt,
            )
            return self._Resp(resp.output_text or "")
        except Exception:
            try:
                resp = self._client.chat.completions.create(
                    model=_openai_model_name(),
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}],
                )
                return self._Resp(resp.choices[0].message.content or "")
            except Exception:
                return self._Resp("")

def configure_model() -> Optional[Any]:
    client = _openai_client()
    if client is None:
        return None
    return _OpenAIModelShim(client)

def heuristic_route(user_input: str) -> Dict[str, Any]:
    t = (user_input or "").lower()

    if any(k in t for k in ["churn", "customer", "cohort", "retention", "subscription"]):
        return {"intent": "unknown", "dataset_match": False}
    if re.search(r"\b20(1\d|2[0134-9])\b", t) and "2022" not in t:
        return {"intent": "unknown", "dataset_match": False}

    if any(k in t for k in ["help", "what can i ask", "what can i do", "who are you"]):
        return {"intent": "unknown", "dataset_match": True}

    if any(k in t for k in ["sample", "show me a sample", "limit"]) and any(k in t for k in ["row", "rows", "records"]):
        return {"intent": "sample_rows", "dataset_match": True}

    if "vendor" in t:
        return {"intent": "vendor_inactivity", "dataset_match": True}
    if "tip" in t and "strip" not in t:
        return {"intent": "tip_trend", "dataset_match": True}
    if any(k in t for k in ["fare", "price", "expensive", "money", "revenue", "cost"]):
        return {"intent": "fare_trend", "dataset_match": True}
    if any(k in t for k in ["trip", "trips", "ride", "rides", "busy", "busier",
                            "frequency", "activity", "volume"]):
        return {"intent": "trip_frequency", "dataset_match": True}

    return {"intent": "unknown", "dataset_match": True}

def ask_router(model: Any | None, user_input: str) -> Dict[str, Any]:
    if model is None:
        return heuristic_route(user_input)
    try:
        prompt = ROUTER_SYSTEM_PROMPT + "\n\nUser request:\n" + user_input
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        data = json.loads(text)
        if not isinstance(data, dict):
            return heuristic_route(user_input)
        return data
    except Exception:
        return heuristic_route(user_input)

def semantic_rewrite(model: Any | None, user_input: str) -> Dict[str, Any]:
    def _fallback():
        r = heuristic_route(user_input)
        return {"rewritten": user_input.strip(), "intent_hint": r.get("intent"), "granularity_hint": None, "metric_hint": None}

    if model is None:
        return _fallback()
    try:
        prompt = REWRITE_SYSTEM_PROMPT + "\n\nUser message:\n" + user_input
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        data = json.loads(text)
        if not isinstance(data, dict) or "rewritten" not in data:
            return _fallback()
        return data
    except Exception:
        return _fallback()
