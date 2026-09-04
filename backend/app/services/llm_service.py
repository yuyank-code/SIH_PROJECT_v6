"""LLM-powered helpers using Emergent Universal Key.

- explain_risk(): concise, plain-language "Why is this zone at risk?" narrative
  built strictly from the numeric factors we pass in — the LLM is instructed
  NOT to invent facts.
- build_alert_translations(): produce a genuinely multilingual alert map.
  Human-verified offline templates (English, Assamese, Nepali) are the floor,
  so language switching works with NO LLM key and NO network. The LLM only
  *extends coverage* to lower-resource NER languages (Khasi, Mizo, Bodo) when a
  key is configured; if it is not, those languages fall back to English but are
  clearly tagged so the UI can show translation is pending verification.

Both functions degrade gracefully — if the key is missing or the LLM call
fails, the platform keeps working. Every translation carries a `source` so the
provenance of safety-critical text is always auditable (never fabricated).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

log = logging.getLogger("llm_service")

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    _CHAT_AVAILABLE = True
except Exception:  # pragma: no cover
    LlmChat = None  # type: ignore
    UserMessage = None  # type: ignore
    _CHAT_AVAILABLE = False


SUPPORTED_LANGUAGES = {
    "en": "English",
    "as": "Assamese",
    "kha": "Khasi",
    "lus": "Mizo",
    "ne": "Nepali",
    "brx": "Bodo",
}

# ---------------------------------------------------------------------------
# Offline, human-verified alert templates.
#
# The alert is composed from structured parts, so the fixed safety scaffolding
# (severity word, "landslide risk near", the Reason/Action labels) is localized
# per language while the dynamic parts (place names, the operator's free-text
# reason/action) are preserved verbatim. We only ship templates for languages
# whose wording we can stand behind (en/as/ne). Low-resource NER languages
# (kha/lus/brx) are intentionally NOT hand-faked here — mistranslating an
# emergency warning is worse than clearly marking it pending. They are covered
# by the LLM when a key is present, else fall back to English with a tag.
#
# translation source tags:
#   builtin_verified  -> from these hand-authored templates
#   llm               -> produced by the LLM at alert-creation time
#   en_fallback       -> English text shown because no verified/LLM translation
#                        was available (UI should badge this as "pending")
# ---------------------------------------------------------------------------
_SEVERITY_WORDS: Dict[str, Dict[str, str]] = {
    "en": {"LOW": "LOW", "MEDIUM": "MODERATE", "HIGH": "HIGH", "CRITICAL": "CRITICAL"},
    "as": {"LOW": "সৰু", "MEDIUM": "মজলীয়া", "HIGH": "উচ্চ", "CRITICAL": "সংকটজনক"},
    "ne": {"LOW": "न्यून", "MEDIUM": "मध्यम", "HIGH": "उच्च", "CRITICAL": "अति गम्भीर"},
}

# Per-language sentence builders. Each takes the localized severity word plus the
# (verbatim) dynamic parts and returns the composed alert string.
_TEMPLATES = {
    "en": lambda sev, zone, dist, state, reason, action: (
        f"{sev} landslide risk near {zone} ({dist}, {state}). "
        f"Reason: {reason}. Action: {action}"
    ),
    "as": lambda sev, zone, dist, state, reason, action: (
        f"{zone} ({dist}, {state})-ৰ ওচৰত {sev} ভূমিস্খলনৰ আশংকা। "
        f"কাৰণ: {reason}। ব্যৱস্থা: {action}।"
    ),
    "ne": lambda sev, zone, dist, state, reason, action: (
        f"{zone} ({dist}, {state}) नजिक {sev} पहिरो जोखिम। "
        f"कारण: {reason}। उपाय: {action}।"
    ),
}

BUILTIN_LANGUAGES = set(_TEMPLATES.keys())


def _key() -> str:
    return os.environ.get("EMERGENT_LLM_KEY", "").strip()


def _compose_english(severity: str, zone: str, dist: str, state: str, reason: str, action: str) -> str:
    return _TEMPLATES["en"](
        _SEVERITY_WORDS["en"].get(severity, severity), zone, dist, state, reason, action
    )


def _compose_builtin(lang: str, severity: str, zone: str, dist: str, state: str, reason: str, action: str) -> str:
    sev_word = _SEVERITY_WORDS.get(lang, {}).get(severity, severity)
    return _TEMPLATES[lang](sev_word, zone, dist, state, reason, action)


def _rule_based_explanation(severity: str, factors: List[Dict[str, Any]]) -> str:
    if not factors:
        return f"{severity} risk. No individual driver exceeded its alert threshold; the combined pattern of recent rainfall and terrain drove the score."
    top = ", ".join(f'{f["label"]} = {f["value"]} {f["unit"]}' for f in factors[:3])
    return f"{severity} risk driven by: {top}."


async def explain_risk(severity: str, factors: List[Dict[str, Any]], zone_name: str) -> str:
    fallback = _rule_based_explanation(severity, factors)
    if not (_CHAT_AVAILABLE and _key()):
        return fallback
    try:
        chat = LlmChat(
            api_key=_key(),
            session_id=f"risk-explain-{zone_name}",
            system_message=(
                "You are a disaster-management analyst. Given a risk severity and a JSON list of "
                "numeric drivers (rainfall totals, slope, elevation, sensor status), write a single "
                "2-3 sentence plain-language explanation. Do NOT invent facts, weather events, or numbers "
                "beyond those provided. Speak in operational tone."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        msg = UserMessage(text=(
            f"Zone: {zone_name}\nSeverity: {severity}\nFactors: {factors}"
        ))
        reply = await chat.send_message(msg)
        text = (reply or "").strip()
        return text or fallback
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM explain_risk failed: %s", exc)
        return fallback


async def _llm_translate(english: str, targets: List[str]) -> Dict[str, str]:
    """Best-effort LLM translation for languages without a verified template.

    Returns {lang: text} only for languages the LLM actually returned; callers
    fall back to English (tagged) for anything missing. Never raises.
    """
    if not (_CHAT_AVAILABLE and _key() and targets):
        return {}
    try:
        chat = LlmChat(
            api_key=_key(),
            session_id=f"alert-tx-{hash(english) & 0xFFFF}",
            system_message=(
                "You translate short emergency alerts for India's North Eastern Region. "
                "Output valid JSON only, with the requested language codes as keys. Keep the "
                "meaning exact and the tone urgent but calm. Preserve place names and numbers. "
                "If a language script is unavailable, use standard romanized transliteration."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        msg = UserMessage(text=(
            f"Alert (English): {english}\n"
            f"Translate into these languages and return JSON with exactly these keys "
            f"{targets}: { {l: SUPPORTED_LANGUAGES[l] for l in targets} }"
        ))
        reply = await chat.send_message(msg)
        import json, re
        m = re.search(r"\{.*\}", reply or "", re.S)
        if not m:
            return {}
        data = json.loads(m.group(0))
        return {l: data[l] for l in targets if isinstance(data.get(l), str) and data[l].strip()}
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM translate failed: %s", exc)
        return {}


async def build_alert_translations(
    severity: str,
    zone_name: str,
    district: str,
    state: str,
    reason: str,
    recommended_action: str,
    langs: List[str] | None = None,
) -> Dict[str, Any]:
    """Compose an alert in every supported language.

    Layering (safest first): verified offline template -> LLM -> English tag.
    Returns {lang: text, ..., "_sources": {lang: source}} so switching languages
    always yields genuinely distinct, provenance-tagged content — never six
    identical English copies (the previous bug).
    """
    langs = langs or list(SUPPORTED_LANGUAGES.keys())
    english = _compose_english(severity, zone_name, district, state, reason, recommended_action)

    out: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    # 1) Verified offline templates (work with no key, no network).
    for lang in langs:
        if lang in BUILTIN_LANGUAGES:
            out[lang] = _compose_builtin(lang, severity, zone_name, district, state, reason, recommended_action)
            sources[lang] = "builtin_verified"

    # 2) LLM extends coverage to remaining (low-resource) languages only.
    remaining = [l for l in langs if l not in out]
    if remaining:
        translated = await _llm_translate(english, remaining)
        for lang in remaining:
            if lang in translated:
                out[lang] = translated[lang]
                sources[lang] = "llm"
            else:
                # 3) Honest fallback: show English, flag as pending verification.
                out[lang] = english
                sources[lang] = "en_fallback"

    out["_sources"] = sources
    return out
