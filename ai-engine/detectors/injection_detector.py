"""
Prompt Injection Detector — Node 6 of the AIMO monitoring pipeline

The only synchronous-capable detector — can run pre-pipeline in ARIA
middleware to log attempts before the LLM sees them.

Detection method:
  1. Regex pattern library (18 patterns across 10 injection types)
  2. pgvector cosine similarity against known injection vectors
     (seeded at startup from ARIA golden_dataset.json adversarial cases)

Always writes to injection_attempts table — full audit log.
Alert fires when: > 3 attempts from same user_id within 60 minutes.

Severity: always P0 — any injection attempt is a safety event.

Phase 1: implement detect() with regex first, then add pgvector similarity
"""
from __future__ import annotations
import re
import os

SIMILARITY_THRESHOLD = float(os.getenv("INJECTION_SIMILARITY_THRESHOLD", "0.85"))

# ── Injection type enum ───────────────────────────────────────

INJECTION_TYPES = {
    "DIRECT_OVERRIDE",
    "AUTHORITY_CLAIM",
    "ROLEPLAY_FRAMING",
    "HTML_COMMENT",
    "CODE_BLOCK_BYPASS",
    "URGENCY_PRESSURE",
    "EMOTIONAL_MANIPULATION",
    "MULTILINGUAL_VARIANT",
    "SYSTEM_TAG",
    "DAN_MODE",
}

# ── Regex patterns (18 patterns, derived from ARIA golden_dataset v1.0.5) ──

PATTERNS: list[tuple[str, str, str]] = [
    # (injection_type, regex_pattern, description)
    ("DIRECT_OVERRIDE",         r"ignore\s+(?:your\s+)?(?:previous|all|the\s+above)?\s*(?:instructions?|rules?|guidelines?|system\s+prompt)",
                                "Classic direct override"),
    ("DIRECT_OVERRIDE",         r"disregard\s+(?:all\s+)?(?:previous|your)\s+(?:instructions?|rules?)",
                                "Disregard variant"),
    ("AUTHORITY_CLAIM",         r"i\s+(?:am|'m)\s+(?:a\s+|an\s+)?(?:teacher|professor|admin(?:istrator)?|developer|expert|instructor)",
                                "Authority claim"),
    ("AUTHORITY_CLAIM",         r"(?:my\s+)?(?:student|access|teacher)\s*(?:id|code|number|pass)\b",
                                "ID/access code claim"),
    ("AUTHORITY_CLAIM",         r"(?:school|university|institution)\s+policy\s+(?:says?|requires?|states?)",
                                "Institutional policy override"),
    ("ROLEPLAY_FRAMING",        r"you\s+are\s+now\s+\w",
                                "Roleplay persona switch"),
    ("ROLEPLAY_FRAMING",        r"(?:pretend|act|behave)\s+(?:you\s+are|as\s+if\s+you(?:\s+are)?|like\s+you(?:\s+are)?)",
                                "Roleplay framing"),
    ("HTML_COMMENT",            r"<!--",
                                "HTML comment injection"),
    ("SYSTEM_TAG",              r"\[system\s*:",
                                "Fake system tag"),
    ("SYSTEM_TAG",              r"\bsystem\s*:\s*(?:set|override|disable|enable)",
                                "Inline system command"),
    ("CODE_BLOCK_BYPASS",       r"```.*(?:are\s+excluded|not\s+(?:apply|subject))",
                                "Code block exclusion claim"),
    ("URGENCY_PRESSURE",        r"(?:exam|test|quiz)\s+(?:is\s+)?in\s+\d+\s+(?:minutes?|hours?)",
                                "Exam urgency"),
    ("URGENCY_PRESSURE",        r"\b(?:i\s+need\s+this?\s+)?(?:NOW|ASAP|URGENT(?:LY)?)\b",
                                "Urgency demand"),
    ("EMOTIONAL_MANIPULATION",  r"i(?:'m|\s+am)\s+(?:going\s+to\s+)?(?:cry|sob|break\s+down)",
                                "Emotional pressure — crying"),
    ("EMOTIONAL_MANIPULATION",  r"(?:i\s+give\s+up|i\s+can'?t\s+(?:do\s+)?this|i'?m\s+so\s+frustrated)",
                                "Frustration/give-up manipulation"),
    ("MULTILINGUAL_VARIANT",    r"ignora(?:r)?\s+(?:tus\s+)?instrucciones",
                                "Spanish direct override"),
    ("MULTILINGUAL_VARIANT",    r"ignorez\s+(?:vos\s+)?instructions",
                                "French direct override"),
    ("DAN_MODE",                r"\b(?:DAN|jailbreak|god\s+mode|developer\s+mode)\b",
                                "DAN / jailbreak keyword"),
]

_COMPILED = [(itype, re.compile(pattern, re.IGNORECASE), desc)
             for itype, pattern, desc in PATTERNS]


def detect_patterns(input_text: str) -> list[dict]:
    """
    Check input_text against all 18 regex patterns.

    Returns list of matches:
      [{ injection_type: str, pattern: str, description: str }, ...]
    Empty list means no patterns matched.
    """
    matches = []
    for injection_type, regex, description in _COMPILED:
        if regex.search(input_text):
            matches.append({
                "injection_type": injection_type,
                "pattern": regex.pattern,
                "description": description,
            })
    return matches


def detect_similarity(input_text: str) -> tuple[float, str | None]:
    """
    Embed input_text and cosine-compare to injection_vectors table.

    Returns (max_similarity, injection_type | None).
    Phase 1: implement pgvector lookup.
    """
    raise NotImplementedError("Phase 1")


def classify(input_text: str) -> dict:
    """
    Full injection classification using patterns + vector similarity.

    Returns:
      {
        injection_detected: bool,
        injection_type:     str | None,
        matched_patterns:   list[str],
        similarity_score:   float | None,
      }
    """
    matches = detect_patterns(input_text)
    injection_detected = len(matches) > 0
    injection_type = matches[0]["injection_type"] if matches else None
    matched_patterns = [m["pattern"] for m in matches]

    # Vector similarity (Phase 1)
    similarity_score = None
    # try:
    #     similarity_score, vector_type = detect_similarity(input_text)
    #     if similarity_score and similarity_score >= SIMILARITY_THRESHOLD:
    #         injection_detected = True
    #         injection_type = injection_type or vector_type

    return {
        "injection_detected": injection_detected,
        "injection_type":     injection_type,
        "matched_patterns":   matched_patterns,
        "similarity_score":   similarity_score,
    }
