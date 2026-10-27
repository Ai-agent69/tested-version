"""
main.py
-------
Entry point for the Hybrid Agentic Memory System.

Required pipeline per user input:
    User Input
        -> Ollama structured memory analysis JSON
        -> Temporary scope goes directly to Trash
        -> Python validation
        -> Python final score for potential long-term memories only
        -> Python threshold decision: LONG_TERM or TRASH
        -> MongoDB storage only for validated LONG_TERM memories

Run:
    python main.py
"""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

from ai.ollama_client import analyze_memory, check_ollama_connection
from database.mongodb import MemoryDatabase, check_mongodb_connection
from memory_evaluator import (
    LONG_TERM_THRESHOLD,
    build_memory_document,
    make_memory_decision,
)
from trash_box import record_trash


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def _print_startup_status() -> None:
    """Print a brief status of Ollama and MongoDB connections at startup."""
    print("\n" + "=" * 60)
    print("Hybrid Agentic Memory System")
    print("=" * 60)

    ollama_status = check_ollama_connection()
    if ollama_status["connected"] and ollama_status["model_found"]:
        print(f"Ollama : CONNECTED | model: {ollama_status['model_used']}")
    elif ollama_status["connected"]:
        print(f"Ollama : CONNECTED | model '{ollama_status['model_used']}' not found")
        print(f"Available models: {ollama_status['available_models']}")
    else:
        print(f"Ollama : UNAVAILABLE | {ollama_status['error']}")

    mongo_status = check_mongodb_connection()
    if mongo_status["connected"]:
        print(f"MongoDB: CONNECTED | db: {mongo_status['db_name']}")
    else:
        print(f"MongoDB: UNAVAILABLE | {mongo_status['error']}")

    print("=" * 60)
    print("Type a statement and press Enter. Type 'quit' or 'exit' to stop.")
    print("=" * 60 + "\n")


def _store_long_term_memory(memory_text: str, analysis: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Store one approved memory document in MongoDB with contradiction & intention fulfillment checking."""
    document = build_memory_document(memory_text, analysis, decision)
    db = MemoryDatabase()

    try:
        db.connect()
    except Exception as exc:
        logger.warning("MongoDB unavailable: %s", exc)
        return {
            "status": "UNAVAILABLE",
            "stored": False,
            "inserted_id": None,
            "error": str(exc),
            "document": document,
        }

    try:
        # Check if detect_contradiction is available and returns an existing conflict
        conflict = None
        if hasattr(db, "detect_contradiction"):
            try:
                res = db.detect_contradiction(memory_text, category=analysis.get("category", ""))
                if isinstance(res, dict) and "_id" in res:
                    conflict = res
            except Exception:
                pass

        if conflict:
            old_id = str(conflict["_id"])
            document["contradicts_memory_id"] = old_id

        inserted_id = db.insert_analyzed_memory(document)

        if conflict and inserted_id and hasattr(db, "supersede_memory"):
            try:
                db.supersede_memory(str(conflict["_id"]), str(inserted_id))
            except Exception:
                pass

        return {
            "status": "STORED",
            "stored": True,
            "inserted_id": inserted_id,
            "error": "",
            "document": document,
            "superseded_id": str(conflict["_id"]) if conflict else None,
        }
    except Exception as exc:
        logger.error("MongoDB storage failed: %s", exc)
        return {
            "status": "FAILED",
            "stored": False,
            "inserted_id": None,
            "error": str(exc),
            "document": document,
        }
    finally:
        db.close()


def process_input(
    user_input: str,
    recent_context: str | None = None,
) -> dict[str, Any]:
    """
    Run the universal memory pipeline on user input.

    Supports atomic segmentation of compound inputs, handles short/long sentences,
    differentiates future intentions from completed events, evaluates each candidate
    independently via Python-authoritative thresholding, checks contradictions, and
    persists long-term memories in MongoDB while retaining temporary items.
    """
    text = (user_input or "").strip()
    if not text:
        return {
            "input": text,
            "pipeline_complete": False,
            "analysis_success": False,
            "stored": False,
            "mongodb_status": "NOT_ATTEMPTED",
            "reason": "Empty input - nothing to process.",
        }

    result: dict[str, Any] = {
        "input": text,
        "pipeline_complete": False,
        "analysis_success": False,
        "stored": False,
        "mongodb_status": "NOT_ATTEMPTED",
    }

    analysis = analyze_memory(text, recent_context=recent_context)
    result["analysis"] = analysis

    if not analysis["success"]:
        result.update(
            {
                "pipeline_complete": False,
                "reason": analysis.get("reason", "Memory analysis failed."),
                "error": analysis.get("error", ""),
            }
        )
        return result

    raw_candidates = analysis.get("extracted_memories")
    if not raw_candidates or not isinstance(raw_candidates, list):
        raw_candidates = [analysis]

    candidate_results: list[dict[str, Any]] = []
    for cand in raw_candidates:
        cand_text = (cand.get("candidate_text") or cand.get("memory_text") or text).strip()
        if not cand.get("memory_scope") and all(
            field in cand for field in ("importance_score", "persistence_score", "usefulness_score")
        ):
            cand["memory_scope"] = "POTENTIAL_LONG_TERM"

        try:
            cand_decision = make_memory_decision(cand, threshold=LONG_TERM_THRESHOLD)
        except (KeyError, TypeError, ValueError) as exc:
            cand_decision = {
                "final_score": None,
                "threshold": LONG_TERM_THRESHOLD,
                "decision": "TEMPORARY",
                "is_longterm": False,
                "scoring_skipped": True,
                "reason": f"Evaluation error: {exc}",
            }

        cand_eval: dict[str, Any] = {
            "candidate_text": cand_text,
            "memory_text": cand_text,
            "memory_type": cand["memory_type"],
            "memory_scope": cand["memory_scope"],
            "category": cand.get("category", "general"),
            "sub_type": cand.get("sub_type", cand.get("category", "general")),
            "is_intention": cand.get("is_intention", False),
            "long_term_beneficial": cand.get("long_term_beneficial", True),
            "final_score": cand_decision["final_score"],
            "threshold": cand_decision["threshold"],
            "decision": cand_decision["decision"],
            "scoring_skipped": cand_decision["scoring_skipped"],
            "reason": cand.get("reason", ""),
            "decision_reason": cand_decision["reason"],
            "stored": False,
            "mongodb_status": "NOT STORED",
            "storage": "NOT STORED",
            "storage_error": "",
        }

        if not cand_decision["scoring_skipped"]:
            cand_eval["importance_score"] = cand.get("importance_score")
            cand_eval["persistence_score"] = cand.get("persistence_score")
            cand_eval["usefulness_score"] = cand.get("usefulness_score")

        if cand_decision["is_longterm"]:
            storage = _store_long_term_memory(cand_text, cand, cand_decision)
            cand_eval["storage"] = storage
            cand_eval["stored"] = storage["stored"]
            cand_eval["mongodb_status"] = storage["status"]
            cand_eval["storage_error"] = storage["error"]
        else:
            trash_entry = record_trash(
                input_text=cand_text,
                memory_type=cand["memory_type"],
                memory_scope=cand["memory_scope"],
                reason=cand.get("reason", ""),
                final_score=cand_decision["final_score"],
                threshold=cand_decision["threshold"],
                scoring_skipped=cand_decision["scoring_skipped"],
            )
            cand_eval["trash_entry"] = trash_entry

        candidate_results.append(cand_eval)

    # Pick authoritative primary candidate (prefer first long-term, else first)
    primary = next(
        (c for c in candidate_results if c.get("decision") == "LONG_TERM"),
        candidate_results[0],
    )

    any_stored = any(c.get("stored") for c in candidate_results)
    primary_stored = any_stored if any_stored else primary["stored"]
    primary_status = "STORED" if any_stored else primary["mongodb_status"]

    result.update(
        {
            "pipeline_complete": True,
            "analysis_success": True,
            "memories": candidate_results,
            "candidate_results": candidate_results,
            "extracted_count": len(candidate_results),
            "stored_count": sum(1 for c in candidate_results if c.get("stored")),
            "memory_type": primary["memory_type"],
            "memory_scope": primary["memory_scope"],
            "category": primary.get("category", "general"),
            "sub_type": primary.get("sub_type", "general"),
            "is_intention": primary.get("is_intention", False),
            "long_term_beneficial": primary["long_term_beneficial"],
            "final_score": primary["final_score"],
            "threshold": primary["threshold"],
            "decision": primary["decision"],
            "scoring_skipped": primary["scoring_skipped"],
            "reason": primary["reason"],
            "decision_reason": primary["decision_reason"],
            "stored": primary_stored,
            "mongodb_status": primary_status,
            "storage": primary["storage"],
            "storage_error": primary["storage_error"],
        }
    )

    if not primary["scoring_skipped"]:
        result.update(
            {
                "importance_score": primary.get("importance_score"),
                "persistence_score": primary.get("persistence_score"),
                "usefulness_score": primary.get("usefulness_score"),
            }
        )

    if "trash_entry" in primary and not primary["stored"]:
        result["trash_entry"] = primary["trash_entry"]

    return result


def _print_result(result: dict[str, Any]) -> None:
    """Display the memory analysis in a clear, test-friendly format."""
    print()
    print("=" * 40)
    print("MEMORY ANALYSIS")
    print("=" * 40)
    print("Input:")
    print(result.get("input", ""))
    print()

    if not result.get("analysis_success"):
        print("Memory Type:")
        print("N/A")
        print()
        print("Decision:")
        print("NOT ANALYZED")
        print()
        print("MongoDB:")
        print(result.get("mongodb_status", "NOT_ATTEMPTED"))
        print()
        print("Reason:")
        print(result.get("reason", "Analysis failed."))
        error = result.get("error")
        if error:
            print()
            print("Error:")
            print(error)
        print("=" * 40)
        return

    memories = result.get("memories", [])
    if len(memories) > 1:
        print(f"Extracted Atomic Memories ({len(memories)}):")
        for idx, mem in enumerate(memories, 1):
            intent_flag = " [FUTURE INTENTION]" if mem.get("is_intention") else ""
            score_info = f"Score: {mem['final_score']:.4f}" if mem.get("final_score") is not None else "Scoring: SKIPPED"
            print(f"  {idx}. [{mem['memory_type']}] ({mem.get('category', 'general')}){intent_flag}: \"{mem.get('candidate_text', '')}\" -> {mem['decision']} ({score_info}) | MongoDB: {mem['mongodb_status']}")
        print()

    print("Memory Type:")
    print(result["memory_type"])
    print()
    print("Memory Scope:")
    print(result["memory_scope"])
    print()

    if result.get("scoring_skipped"):
        print("Decision:")
        print(result["decision"])
        print()
        print("Scoring:")
        print("SKIPPED")
        print()
        print("Storage:")
        print("NOT STORED")
        print()
        print("Reason:")
        print(result["reason"])
        print("=" * 40)
        return

    print("Importance Score:")
    print(f"{result['importance_score']:.4f}")
    print()
    print("Persistence Score:")
    print(f"{result['persistence_score']:.4f}")
    print()
    print("Usefulness Score:")
    print(f"{result['usefulness_score']:.4f}")
    print()
    print("Final Score:")
    print(f"{result['final_score']:.4f}")
    print()
    print("Threshold:")
    print(f"{result['threshold']:.2f}")
    print()
    print("Decision:")
    print(result["decision"])
    print()
    if result["decision"] == "LONG_TERM":
        print("MongoDB:")
        print(result["mongodb_status"])
        if result.get("storage_error"):
            print(result["storage_error"])
    else:
        print("Storage:")
        print("NOT STORED")
    print()
    print("Reason:")
    print(result["reason"])
    print("=" * 40)


def main() -> None:
    _print_startup_status()

    recent_context: str | None = None

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            sys.exit(0)

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            sys.exit(0)

        if not user_input:
            print("(Empty input - please type something.)")
            continue

        result = process_input(user_input, recent_context)
        _print_result(result)
        recent_context = user_input


if __name__ == "__main__":
    main()
