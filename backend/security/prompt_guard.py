"""Prompt Injection 방어 노드."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Maximum allowed input length (characters)
MAX_INPUT_LENGTH: int = 10_000

# Risk score threshold -- inputs scoring at or above this are blocked
INJECTION_RISK_THRESHOLD: float = 0.7

# --- English injection patterns (original) --------------------------------

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
]

# --- Korean-language injection patterns ------------------------------------

KOREAN_INJECTION_PATTERNS = [
    re.compile(r"이전\s*지시를?\s*무시", re.IGNORECASE),       # "이전 지시를 무시"
    re.compile(r"시스템\s*프롬프트", re.IGNORECASE),            # "시스템 프롬프트"
    re.compile(r"너는\s*이제부터", re.IGNORECASE),              # "너는 이제부터"
    re.compile(r"역할을?\s*바꿔", re.IGNORECASE),               # "역할을 바꿔"
    re.compile(r"이전\s*(명령|지침)을?\s*(모두\s*)?(무시|잊어)", re.IGNORECASE),
    re.compile(r"새로운\s*역할", re.IGNORECASE),                # "새로운 역할"
]

# --- Jailbreak detection patterns ------------------------------------------

JAILBREAK_PATTERNS = [
    # DAN (Do Anything Now) variants
    re.compile(r"\bDAN\b", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"jailbreak(ed)?", re.IGNORECASE),
    # Hypothetical / roleplay bypass
    re.compile(r"hypothetically[\s,]", re.IGNORECASE),
    re.compile(r"in\s+a\s+hypothetical\s+scenario", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?(you\s+are\s+)?an?\s+", re.IGNORECASE),
    re.compile(r"role\s*play\s+as\s+", re.IGNORECASE),
    # Token smuggling / delimiter abuse
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"<\|endoftext\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    # Developer mode
    re.compile(r"developer\s+mode\s+(enabled|on|activated)", re.IGNORECASE),
]

# Weighted scoring: each pattern category has a base weight
_PATTERN_WEIGHTS: dict[str, tuple[list[re.Pattern], float]] = {
    "injection_en": (INJECTION_PATTERNS, 0.45),
    "injection_ko": (KOREAN_INJECTION_PATTERNS, 0.45),
    "jailbreak": (JAILBREAK_PATTERNS, 0.35),
}


def score_injection_risk(text: str) -> float:
    """Return a 0.0 -- 1.0 risk score for prompt injection / jailbreak.

    The score is computed by accumulating weights from matched pattern
    categories and clamping to [0.0, 1.0].
    """
    if not text:
        return 0.0

    score = 0.0

    # Length-based heuristic: extremely long inputs get a small bump
    if len(text) > MAX_INPUT_LENGTH:
        score += 0.15

    for category, (patterns, weight) in _PATTERN_WEIGHTS.items():
        matches = sum(1 for p in patterns if p.search(text))
        if matches:
            # First match contributes the full weight; additional matches add
            # a diminishing increment (up to 2x the base weight for the
            # category).
            category_score = weight + min(matches - 1, 3) * (weight * 0.15)
            score += category_score

    return min(round(score, 4), 1.0)


def detect_injection(text: str) -> bool:
    """Return True if any injection or jailbreak pattern is found."""
    all_patterns = INJECTION_PATTERNS + KOREAN_INJECTION_PATTERNS + JAILBREAK_PATTERNS
    return any(p.search(text) for p in all_patterns)


def sanitize_input(text: str) -> str:
    """위험 패턴을 제거하고 정제된 텍스트 반환.

    Validates length, scores injection risk, and logs any detected attempts.
    """
    if len(text) > MAX_INPUT_LENGTH:
        logger.warning(
            "Input exceeds maximum length (%d > %d), truncating",
            len(text),
            MAX_INPUT_LENGTH,
        )
        text = text[:MAX_INPUT_LENGTH]

    risk = score_injection_risk(text)

    if risk >= INJECTION_RISK_THRESHOLD:
        logger.warning(
            "Prompt injection detected (risk=%.4f, threshold=%.2f): %s",
            risk,
            INJECTION_RISK_THRESHOLD,
            text[:200],
        )
        raise ValueError(
            f"Prompt injection detected (risk score {risk:.2f} "
            f"exceeds threshold {INJECTION_RISK_THRESHOLD:.2f})"
        )

    if detect_injection(text):
        logger.warning(
            "Prompt injection pattern matched (risk=%.4f): %s",
            risk,
            text[:200],
        )
        raise ValueError("Prompt injection detected")

    return text.strip()
