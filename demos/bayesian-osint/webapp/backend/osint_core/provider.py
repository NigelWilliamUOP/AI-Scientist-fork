"""Request construction only. Secrets and HTTP calls do not belong in this module."""
from __future__ import annotations
import json
from typing import Any

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

def answer_request(*, model: str, system_prompt: str, question: str,
                   evidence: list[dict[str, Any]], schema: dict[str, Any],
                   mode: str, cutoff: str | None = None,
                   approved_providers: tuple[str, ...] = (),
                   max_input_chars: int = 40000, max_output_tokens: int = 1600) -> dict:
    if not model or "/" not in model or "latest" in model.lower() or model.startswith("~"):
        raise ValueError("choose an explicit configured model slug, not a latest alias")
    if mode not in {"CURRENT_INVESTIGATION", "HISTORICAL_RECONSTRUCTION", "RECORDED_REPLAY", "SYNTHETIC_TRAINING"}:
        raise ValueError("invalid mode")
    if mode == "RECORDED_REPLAY":
        raise ValueError("recorded replay must not make a new model call")
    if mode == "HISTORICAL_RECONSTRUCTION" and not cutoff:
        raise ValueError("historical reconstruction requires cutoff")
    if not evidence:
        raise ValueError("no admitted evidence")
    if not question.strip() or len(question) > 4000:
        raise ValueError("invalid question length")
    if isinstance(max_output_tokens, bool) or not 1 <= max_output_tokens <= 4000:
        raise ValueError("output token ceiling outside reference policy")
    payload = json.dumps({"question": question, "mode": mode, "cutoff": cutoff,
                          "admitted_evidence": evidence}, ensure_ascii=False)
    if len(system_prompt) + len(payload) > max_input_chars:
        raise ValueError("input exceeds configured bound")
    provider = {"require_parameters": True, "allow_fallbacks": False}
    if approved_providers:
        provider["only"] = list(approved_providers)
    return {"model": model,
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": payload}],
            "provider": provider, "max_tokens": max_output_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "grounded_answer", "strict": True, "schema": schema}}}
