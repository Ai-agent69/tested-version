"""
context_analysis.py
────────────────────
Analyzes whether a piece of user input is contextually relevant — i.e.,
whether it relates meaningfully to what is currently being discussed or
to established background context.

This module uses lightweight heuristic scoring (no LLM) to produce a
context_score in the range [0.0, 1.0].

Rationale for NOT using an LLM here:
    The context analysis is a fast, cheap gate that runs before any LLM
    call.  It filters out noise (greetings, trivial filler, commands) so
    that expensive Ollama inference is only invoked when the input
    genuinely warrants memory storage.

Score interpretation:
    0.0 – 0.29  : Off-topic / no meaningful content
    0.30 – 0.59 : Marginally relevant
    0.60 – 1.0  : Clearly relevant / informationally rich
"""

import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONTEXT_THRESHOLD: float = float(os.getenv("CONTEXT_THRESHOLD", "0.3"))

# Short, content-free phrases that score near zero
_NOISE_PATTERNS: list[str] = [
    r"^\s*(hi|hello|hey|yo|sup|howdy|greetings)\s*[!.?]*\s*$",
    r"^\s*(ok|okay|sure|yes|no|nope|yep|nah|k)\s*[!.?]*\s*$",
    r"^\s*(thanks|thank you|thx|ty|cheers)\s*[!.?]*\s*$",
    r"^\s*(bye|goodbye|see you|cya|later)\s*[!.?]*\s*$",
    r"^\s*(lol|haha|hehe|lmao|rofl)\s*[!.?]*\s*$",
]
_NOISE_RE = [re.compile(p, re.IGNORECASE) for p in _NOISE_PATTERNS]

# Words that signal substantive, memorable content
_CONTENT_SIGNALS: list[str] = [
    # factual / definitional
    "is", "are", "was", "were", "means", "defined", "definition",
    "refers", "called", "known", "fact", "information",
    # procedural
    "how", "step", "steps", "procedure", "method", "process", "workflow",
    "first", "then", "next", "finally", "follow",
    # episodic
    "decided", "happened", "occurred", "yesterday", "today", "last",
    "meeting", "team", "project", "learned", "discovered", "realized",
    "experience", "event", "when", "while",
    # conceptual depth & domain terms
    "because", "therefore", "result", "cause", "effect", "reason",
    "important", "remember", "note", "always", "never",
    "database", "document", "data", "memory", "store", "system",
    "model", "api", "code", "mongodb", "sqlite",
]

# Structural richness bonuses
_MIN_WORDS_FOR_BONUS = 6


def _is_noise(text: str) -> bool:
    """Return True if the input matches a known noise pattern."""
    return any(p.match(text) for p in _NOISE_RE)


def _word_count(text: str) -> int:
    return len(text.split())


def _content_signal_count(text: str) -> int:
    lower = text.lower()
    return sum(1 for signal in _CONTENT_SIGNALS if re.search(r"\b" + signal + r"\b", lower))


def analyze_context(
    user_input: str,
    recent_context: Optional[str] = None,
) -> dict:
    """
    Analyze the contextual relevance of *user_input*.

    Parameters
    ----------
    user_input : str
        The raw text from the user.
    recent_context : str, optional
        A summary or snippet of the most recent conversation context.
        When provided, overlap is used to boost the score slightly.

    Returns
    -------
    dict with keys:
        context_score  : float  — 0.0 to 1.0
        is_relevant    : bool   — True if score >= CONTEXT_THRESHOLD
        reason         : str    — human-readable explanation
    """
    text = (user_input or "").strip()

    # ── Guard: empty input ─────────────────────────────────────────────────
    if not text:
        return {
            "context_score": 0.0,
            "is_relevant": False,
            "reason": "Empty input — nothing to analyze.",
        }

    # ── Guard: noise / trivial filler ─────────────────────────────────────
    if _is_noise(text):
        return {
            "context_score": 0.05,
            "is_relevant": False,
            "reason": "Input is a conversational filler with no informational content.",
        }

    score = 0.0
    reasons: list[str] = []

    # ── Length bonus ───────────────────────────────────────────────────────
    words = _word_count(text)
    if words >= _MIN_WORDS_FOR_BONUS:
        length_bonus = min(0.25, words * 0.02)  # caps at 0.25
        score += length_bonus
        reasons.append(f"Sentence length ({words} words) contributes {length_bonus:.2f}.")
    else:
        length_bonus = words * 0.02
        score += length_bonus
        reasons.append(f"Short sentence ({words} words), small length contribution {length_bonus:.2f}.")

    # ── Content signal bonus ───────────────────────────────────────────────
    signals = _content_signal_count(text)
    signal_bonus = min(0.40, signals * 0.08)
    score += signal_bonus
    if signals:
        reasons.append(f"{signals} content signal(s) detected (+{signal_bonus:.2f}).")

    # ── Sentence structure: contains verb + noun-like structure ───────────
    has_verb = bool(re.search(r"\b(is|are|was|were|have|has|had|will|can|should|must|need|"
                              r"decided|happened|learned|know|use|want|need|build|create|"
                              r"store|analyze|classify|remember|understand)\b", text, re.I))
    if has_verb:
        score += 0.15
        reasons.append("Contains a meaningful verb (+0.15).")

    # ── Context overlap (if recent_context provided) ───────────────────────
    if recent_context:
        input_words = set(text.lower().split())
        context_words = set(recent_context.lower().split())
        # Remove stopwords for overlap
        stopwords = {"a", "an", "the", "is", "are", "was", "were", "it", "i", "to", "of", "in", "and", "or"}
        overlap = (input_words - stopwords) & (context_words - stopwords)
        overlap_bonus = min(0.20, len(overlap) * 0.04)
        score += overlap_bonus
        if overlap:
            reasons.append(f"Overlaps with recent context ({len(overlap)} word(s), +{overlap_bonus:.2f}).")

    # ── Clamp ─────────────────────────────────────────────────────────────
    score = round(min(1.0, max(0.0, score)), 4)
    is_relevant = score >= CONTEXT_THRESHOLD

    return {
        "context_score": score,
        "is_relevant": is_relevant,
        "reason": " ".join(reasons) if reasons else "No strong context signals found.",
    }
