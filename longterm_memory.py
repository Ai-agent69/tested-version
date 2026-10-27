"""
longterm_memory.py
------------------
Compatibility wrapper for the Python-owned long-term memory decision.

The main pipeline no longer runs context, importance, and persistence gates
before Ollama. Ollama first returns structured analysis, then Python calculates:

    final_score =
        importance_score * 0.35
        + persistence_score * 0.35
        + usefulness_score * 0.30

and compares it with LONG_TERM_THRESHOLD.
"""

from __future__ import annotations

from memory_evaluator import LONG_TERM_THRESHOLD as LONGTERM_THRESHOLD
from memory_evaluator import calculate_final_score


def decide_longterm(
    importance_score: float,
    persistence_score: float,
    usefulness_score: float,
) -> dict:
    """
    Decide whether validated Ollama scores qualify for long-term storage.

    This function is retained for older imports. New code should prefer
    memory_evaluator.make_memory_decision when the full analysis dict is
    available.
    """
    final_score = calculate_final_score(
        importance_score,
        persistence_score,
        usefulness_score,
    )
    is_longterm = final_score >= LONGTERM_THRESHOLD
    decision = "LONG_TERM" if is_longterm else "TEMPORARY"

    return {
        "is_longterm": is_longterm,
        "final_score": final_score,
        "combined_score": final_score,
        "threshold": LONGTERM_THRESHOLD,
        "decision": decision,
        "reason": (
            f"Final score {final_score:.4f} "
            f"{'>=' if is_longterm else '<'} threshold {LONGTERM_THRESHOLD:.2f}."
        ),
    }
