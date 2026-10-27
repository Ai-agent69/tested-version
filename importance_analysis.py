"""
importance_analysis.py
───────────────────────
Analyzes how important a piece of information is to remember.

Produces an importance_score in the range [0.0, 1.0] using heuristic
signals.  High-scoring inputs contain definitional, consequential, or
knowledge-dense content.  Low-scoring inputs are transient, trivial, or
opinion-free.

Score interpretation:
    0.0 – 0.39  : Not important enough to remember long-term
    0.40 – 0.69 : Moderately important
    0.70 – 1.0  : Highly important — strong candidate for memory storage
"""

import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMPORTANCE_THRESHOLD: float = float(os.getenv("IMPORTANCE_THRESHOLD", "0.4"))

# High-importance signal words — these suggest memorable, durable content
_HIGH_IMPORTANCE_SIGNALS: list[str] = [
    # definitional
    "is a", "is an", "is the", "are a", "are the",
    "means", "defined as", "definition", "refers to", "called",
    "known as", "stands for", "oriented", "described as",
    # factual permanence
    "always", "never", "every", "all", "none", "must",
    # consequential
    "decided", "agreed", "conclusion", "therefore", "result",
    "because", "due to", "leads to", "causes", "effect",
    # learning / discovery
    "learned", "discovered", "realized", "found out", "understood",
    "figured out", "noticed", "remember",
    # procedural sequence
    "first", "step", "steps", "then", "next", "finally",
    "procedure", "method", "process", "workflow", "approach",
    # technical
    "database", "algorithm", "api", "function", "class",
    "module", "library", "framework", "architecture", "system",
    "model", "server", "client", "protocol", "format", "schema",
    "nosql", "sql", "query", "collection", "document", "storage",
    "language", "programming", "interface", "structure",
]

# Low-importance signal words — transient/trivial content
_LOW_IMPORTANCE_SIGNALS: list[str] = [
    "maybe", "perhaps", "i think", "not sure", "might", "could be",
    "just asking", "wondering", "random", "whatever", "anyway",
    "just", "kinda", "sorta",
]

# Structural markers of importance
_IMPORTANT_MARKERS = re.compile(
    r"\b(important|critical|essential|key|note|remember|always|must|"
    r"never|required|necessary|fundamental|core|main|primary|crucial)\b",
    re.IGNORECASE,
)


def _score_signals(text: str) -> tuple[float, list[str]]:
    """Return (bonus_score, list_of_reason_strings) based on signal matching."""
    lower = text.lower()
    score = 0.0
    reasons: list[str] = []

    # High-importance phrases
    found_high = [s for s in _HIGH_IMPORTANCE_SIGNALS if s in lower]
    if found_high:
        bonus = min(0.45, len(found_high) * 0.09)
        score += bonus
        reasons.append(f"High-importance signals ({len(found_high)}): {', '.join(found_high[:3])} → +{bonus:.2f}.")

    # Low-importance phrases — these reduce the score
    found_low = [s for s in _LOW_IMPORTANCE_SIGNALS if s in lower]
    if found_low:
        penalty = min(0.30, len(found_low) * 0.08)
        score -= penalty
        reasons.append(f"Low-importance / uncertainty signals ({len(found_low)}) → -{penalty:.2f}.")

    # Important-marker words (always, must, critical, etc.)
    markers = _IMPORTANT_MARKERS.findall(text)
    if markers:
        bonus = min(0.20, len(markers) * 0.07)
        score += bonus
        reasons.append(f"Importance markers ({markers[:3]}) → +{bonus:.2f}.")

    return score, reasons


def analyze_importance(user_input: str) -> dict:
    """
    Assess how important *user_input* is to store as memory.

    Parameters
    ----------
    user_input : str
        The raw text from the user.

    Returns
    -------
    dict with keys:
        importance_score : float  — 0.0 to 1.0
        is_important     : bool   — True if score >= IMPORTANCE_THRESHOLD
        reason           : str    — human-readable explanation
    """
    text = (user_input or "").strip()

    # ── Guard ─────────────────────────────────────────────────────────────
    if not text:
        return {
            "importance_score": 0.0,
            "is_important": False,
            "reason": "Empty input — nothing to analyze.",
        }

    score = 0.0
    reasons: list[str] = []

    # ── Base score from word count ─────────────────────────────────────────
    words = len(text.split())
    base = min(0.20, words * 0.015)
    score += base
    reasons.append(f"Word count ({words}) base contribution: +{base:.2f}.")

    # ── Signal-based scoring ───────────────────────────────────────────────
    signal_score, signal_reasons = _score_signals(text)
    score += signal_score
    reasons.extend(signal_reasons)

    # ── Specificity bonus: named entities / digits / proper nouns ─────────
    has_named_entity = bool(re.search(r"\b[A-Z][a-zA-Z0-9_-]*\b", text))
    has_number = bool(re.search(r"\b\d+[\d.,]*\b", text))
    if has_named_entity:
        score += 0.10
        reasons.append("Contains proper noun / named entity (+0.10).")
    if has_number:
        score += 0.05
        reasons.append("Contains numeric value (+0.05).")

    # ── Clamp ─────────────────────────────────────────────────────────────
    score = round(min(1.0, max(0.0, score)), 4)
    is_important = score >= IMPORTANCE_THRESHOLD

    return {
        "importance_score": score,
        "is_important": is_important,
        "reason": " ".join(reasons) if reasons else "No strong importance signals found.",
    }
