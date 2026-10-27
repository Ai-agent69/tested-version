"""
memory_evaluator.py
-------------------
Python-owned routing, scoring, and storage decisions for analyzed memories.

Ollama supplies the memory type, memory scope, and analytical scores only for
potential long-term memories. This module skips scoring for temporary inputs,
calculates the final score for candidates, and makes the deterministic
threshold decision.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

LONG_TERM_THRESHOLD: float = float(os.getenv("LONGTERM_THRESHOLD", "0.70"))

IMPORTANCE_WEIGHT: float = float(os.getenv("IMPORTANCE_WEIGHT", "0.35"))
PERSISTENCE_WEIGHT: float = float(os.getenv("PERSISTENCE_WEIGHT", "0.35"))
USEFULNESS_WEIGHT: float = float(os.getenv("USEFULNESS_WEIGHT", "0.30"))
TEMPORARY_SCOPE = "TEMPORARY"
POTENTIAL_LONG_TERM_SCOPE = "POTENTIAL_LONG_TERM"


def _validate_score(score: Any, field_name: str) -> float:
    if isinstance(score, bool):
        raise ValueError(f"{field_name} must be numeric, got boolean.")
    try:
        value = float(score)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")
    return value


def _validate_threshold(threshold: Any) -> float:
    return _validate_score(threshold, "threshold")


def calculate_final_score(
    importance_score: float,
    persistence_score: float,
    usefulness_score: float,
) -> float:
    """Calculate the final memory score using the required weighted formula."""
    importance = _validate_score(importance_score, "importance_score")
    persistence = _validate_score(persistence_score, "persistence_score")
    usefulness = _validate_score(usefulness_score, "usefulness_score")
    final_score = (
        importance * IMPORTANCE_WEIGHT
        + persistence * PERSISTENCE_WEIGHT
        + usefulness * USEFULNESS_WEIGHT
    )
    return round(final_score, 4)


def make_memory_decision(
    analysis: dict[str, Any],
    threshold: float = LONG_TERM_THRESHOLD,
) -> dict[str, Any]:
    """
    Decide whether a validated analysis should be stored long-term.

    TEMPORARY scope goes directly to Trash. Only POTENTIAL_LONG_TERM scope is
    scored. The Ollama long_term_beneficial field is retained as an analytical
    signal, but Python's final score and threshold are authoritative.
    """
    memory_scope = (analysis.get("memory_scope") or "").strip().upper()
    # Compatibility for persisted/legacy analyzer responses that predate the
    # explicit routing field. Score-bearing payloads are still evaluated by
    # the same deterministic threshold, never trusted blindly.
    if not memory_scope and all(field in analysis for field in (
        "importance_score", "persistence_score", "usefulness_score"
    )):
        memory_scope = POTENTIAL_LONG_TERM_SCOPE
    normalized_threshold = _validate_threshold(threshold)

    if memory_scope == TEMPORARY_SCOPE:
        return {
            "final_score": None,
            "threshold": normalized_threshold,
            "decision": "TEMPORARY",
            "is_longterm": False,
            "scoring_skipped": True,
            "reason": "Temporary memory scope; scoring skipped.",
        }

    if memory_scope != POTENTIAL_LONG_TERM_SCOPE:
        raise ValueError(
            "memory_scope must be TEMPORARY or POTENTIAL_LONG_TERM before "
            "making a memory decision."
        )

    final_score = calculate_final_score(
        analysis["importance_score"],
        analysis["persistence_score"],
        analysis["usefulness_score"],
    )
    is_longterm = final_score >= normalized_threshold
    decision = "LONG_TERM" if is_longterm else "TEMPORARY"

    return {
        "final_score": final_score,
        "threshold": normalized_threshold,
        "decision": decision,
        "is_longterm": is_longterm,
        "scoring_skipped": False,
        "reason": (
            f"Final score {final_score:.4f} "
            f"{'>=' if is_longterm else '<'} threshold {normalized_threshold:.2f}."
        ),
    }


def build_memory_document(
    memory_text: str,
    analysis: dict[str, Any],
    decision: dict[str, Any],
    user_id: str = "default_user",
    conversation_id: str = "default_conversation",
) -> dict[str, Any]:
    """Build the MongoDB document for a validated memory."""
    text = (memory_text or "").strip()
    is_longterm = decision.get("is_longterm", True)
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "memory_text": text,
        "memory": text,
        "candidate_text": text,
        "memory_type": analysis["memory_type"],
        "memory_scope": analysis.get("memory_scope", "POTENTIAL_LONG_TERM"),
        "category": analysis.get("category", "general"),
        "sub_type": analysis.get("sub_type", analysis.get("category", "general")),
        "is_intention": bool(analysis.get("is_intention", False)),
        "long_term_beneficial": analysis.get("long_term_beneficial", True),
        "decision": decision["decision"],
        "retention_status": "long_term" if is_longterm else "temporary",
        "is_longterm": is_longterm,
        "reason": analysis.get("reason", ""),
        "decision_reason": decision.get("reason", ""),
        "user_id": analysis.get("user_id", user_id),
        "conversation_id": analysis.get("conversation_id", conversation_id),
        "created_at": now_iso,
        "updated_at": now_iso,
        "related_memory_ids": list(analysis.get("related_memory_ids") or []),
        "contradicts_memory_id": analysis.get("contradicts_memory_id", None),
        "source": analysis.get("source", "user_message"),
    }
    if "importance_score" in analysis and analysis["importance_score"] is not None:
        doc["importance_score"] = round(float(analysis["importance_score"]), 4)
    if "persistence_score" in analysis and analysis["persistence_score"] is not None:
        doc["persistence_score"] = round(float(analysis["persistence_score"]), 4)
    if "usefulness_score" in analysis and analysis["usefulness_score"] is not None:
        doc["usefulness_score"] = round(float(analysis["usefulness_score"]), 4)
    if decision.get("final_score") is not None:
        doc["final_score"] = round(float(decision["final_score"]), 4)
    return doc
