"""FastAPI surface for the Baby Agentic Memory System.

Run with: uvicorn api:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ai.ollama_client import check_ollama_connection, generate_baby_response
from database.mongodb import MemoryDatabase, check_mongodb_connection
from main import process_input

app = FastAPI(title="MASH Agentic Memory API", version="1.0.0")
origins = [value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:5173,http://localhost:3000").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class MemoryInput(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    recent_context: Optional[str] = Field(default=None, max_length=12000)


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    memory_type: str = Field(default="SEMANTIC")
    importance_score: float = Field(default=0.8, ge=0.0, le=1.0)
    persistence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    usefulness_score: float = Field(default=0.8, ge=0.0, le=1.0)
    reason: str = Field(default="Direct memory creation", max_length=1000)
    user_id: str = Field(default="default_user", max_length=100)
    category: str = Field(default="general", max_length=100)
    is_temporary: bool = Field(default=False)


class ChatInput(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    recent_context: Optional[str] = Field(default=None, max_length=12000)
    conversation_id: Optional[str] = Field(default=None, max_length=100)
    user_id: Optional[str] = Field(default="default_user", max_length=100)


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", min_length=1, max_length=200)
    user_id: str = Field(default="default_user", max_length=100)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: Optional[str] = Field(default="", max_length=50000)
    category: Optional[str] = Field(default="general", max_length=100)
    metadata: Optional[dict[str, Any]] = None


class MemoryUpdate(BaseModel):
    memory_text: Optional[str] = Field(default=None, min_length=1, max_length=12000)
    category: Optional[str] = Field(default=None, max_length=100)
    sub_type: Optional[str] = Field(default=None, max_length=100)
    importance_score: Optional[float] = Field(default=None, ge=0, le=1)
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    source: Optional[str] = Field(default=None, max_length=500)
    related_memory_ids: Optional[list[str]] = None


def _memory_view(memory: dict[str, Any]) -> dict[str, Any]:
    """Stable frontend DTO while retaining all validated stored fields."""
    return {
        "id": str(memory.get("_id", memory.get("id", ""))),
        "content": memory.get("memory_text") or memory.get("memory", ""),
        "memory_type": memory.get("memory_type", "OTHER").lower(),
        "sub_type": memory.get("sub_type", memory.get("memory_type", "OTHER")).lower(),
        "category": memory.get("category", ""),
        "is_intention": bool(memory.get("is_intention", False)),
        "importance": memory.get("importance_score"),
        "relevance": memory.get("final_score"),
        "confidence": memory.get("confidence_score", memory.get("usefulness_score", memory.get("classification_confidence"))),
        "retention_status": memory.get("retention_status", "long_term" if memory.get("is_longterm", True) else "temporary"),
        "is_longterm": memory.get("is_longterm", True),
        "created_at": memory.get("created_at"),
        "updated_at": memory.get("updated_at"),
        "expires_at": memory.get("expires_at"),
        "last_accessed": memory.get("last_accessed"),
        "access_count": memory.get("access_count", 0),
        "related_memories": memory.get("related_memory_ids", []),
        "contradicts_memory_id": memory.get("contradicts_memory_id"),
        "source": memory.get("source", "user_input"),
    }


def _db() -> MemoryDatabase:
    database = MemoryDatabase()
    try:
        database.connect()
        return database
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {exc}") from exc


@app.get("/health")
def health() -> dict[str, Any]:
    ollama = check_ollama_connection()
    mongodb = check_mongodb_connection()
    return {
        "status": "healthy" if ollama["connected"] and mongodb["connected"] else "degraded",
        "agent": "MASH",
        "ollama": {"status": "connected" if ollama["connected"] and ollama["model_found"] else "disconnected", **ollama},
        "mongodb": {"status": "connected" if mongodb["connected"] else "disconnected", **mongodb},
    }


@app.post("/memory/process")
def memory_process(payload: MemoryInput) -> dict[str, Any]:
    result = process_input(payload.content, payload.recent_context)
    if not result.get("analysis_success"):
        raise HTTPException(status_code=502, detail=result.get("reason", "Memory processing failed."))

    try:
        database = MemoryDatabase()
        database.connect()
        try:
            database.record_processing_log({
                "input": payload.content,
                "memory_type": result.get("memory_type", "N/A"),
                "memory_scope": result.get("memory_scope", "N/A"),
                "decision": result.get("decision", "N/A"),
                "final_score": result.get("final_score"),
                "threshold": result.get("threshold"),
                "reason": result.get("reason", ""),
                "stored": result.get("stored", False),
            })
        finally:
            database.close()
    except Exception:
        pass

    return result


@app.post("/chat")
def chat(payload: ChatInput) -> dict[str, Any]:
    # Processing first ensures new durable information can participate in future retrieval
    processing = process_input(payload.content, payload.recent_context)
    database = _db()
    conv_id = payload.conversation_id
    try:
        if not conv_id:
            conv_id = database.create_conversation(title=payload.content[:50], user_id=payload.user_id)

        # Retrieve relevant memories
        memories = database.get_relevant_memories(payload.content, limit=8, user_id=payload.user_id)

        # Retrieve conversation history if available
        history_msgs = database.get_messages(conv_id, limit=6)
        history = [{"role": msg["role"], "content": msg["content"]} for msg in history_msgs]
    finally:
        database.close()

    answer = generate_baby_response(payload.content, memories)
    if not answer["success"]:
        raise HTTPException(status_code=503, detail="Ollama unavailable: " + answer["error"])

    # Record messages and audit log in conversation
    try:
        db_rec = _db()
        try:
            db_rec.add_message(conv_id, "user", payload.content, user_id=payload.user_id)
            db_rec.add_message(conv_id, "assistant", answer["response"], memories_used=memories, user_id=payload.user_id)
            db_rec.record_processing_log({
                "input": payload.content,
                "memory_type": processing.get("memory_type", "N/A"),
                "memory_scope": processing.get("memory_scope", "N/A"),
                "decision": processing.get("decision", "N/A"),
                "final_score": processing.get("final_score"),
                "threshold": processing.get("threshold"),
                "reason": processing.get("reason", ""),
                "stored": processing.get("stored", False),
                "conversation_id": conv_id,
            })
        finally:
            db_rec.close()
    except Exception:
        pass

    return {
        "agent": "MASH",
        "response": answer["response"],
        "conversation_id": conv_id,
        "memories_used": [_memory_view(memory) for memory in memories],
        "memory_processing": processing,
    }


@app.post("/memories", status_code=201)
def create_memory(payload: MemoryCreate) -> dict[str, Any]:
    database = _db()
    try:
        final_score = round(payload.importance_score * 0.35 + payload.persistence_score * 0.35 + payload.usefulness_score * 0.30, 4)
        doc = {
            "memory_text": payload.content,
            "memory": payload.content,
            "memory_type": payload.memory_type.upper(),
            "category": payload.category,
            "importance_score": payload.importance_score,
            "persistence_score": payload.persistence_score,
            "usefulness_score": payload.usefulness_score,
            "confidence_score": payload.usefulness_score,
            "final_score": final_score,
            "decision": "TEMPORARY" if payload.is_temporary else "LONG_TERM",
            "long_term_beneficial": not payload.is_temporary,
            "reason": payload.reason,
            "user_id": payload.user_id,
        }
        if payload.is_temporary:
            inserted_id = database.insert_temporary_memory(doc)
            doc["_id"] = inserted_id
            return _memory_view(doc)
        else:
            inserted_id = database.insert_analyzed_memory(doc)
            created = database.get_memory_by_id(inserted_id)
            return _memory_view(created) if created else {"id": inserted_id, "content": payload.content, "status": "created"}
    finally:
        database.close()


@app.get("/memories")
def memories(
    type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, Any]:
    database = _db()
    try:
        if type and type.lower() not in {"long_term", "semantic", "episodic", "procedural", "temporary", "other"}:
            raise HTTPException(status_code=422, detail="Unsupported memory type.")

        if search:
            records = database.get_relevant_memories(search, limit=limit)
        elif type and type.lower() == "temporary":
            records = database.get_temporary_memories(limit=limit)
        elif type and type.lower() not in {"long_term", "temporary"}:
            records = database.get_memories_by_type(type, limit)
        else:
            records = database.get_all_memories(limit)

        if status and status.lower() != "all":
            records = [r for r in records if (r.get("retention_status") or "").lower() == status.lower()]

        return {"items": [_memory_view(record) for record in records], "count": len(records)}
    finally:
        database.close()


@app.get("/memories/search")
def search_memories(q: str = Query(min_length=1), limit: int = Query(default=8, ge=1, le=50)) -> dict[str, Any]:
    database = _db()
    try:
        records = database.get_relevant_memories(q, limit)
        return {"items": [_memory_view(record) for record in records], "count": len(records)}
    finally:
        database.close()


@app.get("/memories/{memory_id}")
def memory_by_id(memory_id: str) -> dict[str, Any]:
    database = _db()
    try:
        memory = database.get_memory_by_id(memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found.")
        return _memory_view(memory)
    finally:
        database.close()


@app.put("/memories/{memory_id}")
def update_memory_endpoint(memory_id: str, payload: MemoryUpdate) -> dict[str, Any]:
    database = _db()
    try:
        updates = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True)
        memory = database.update_memory(memory_id, updates)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found or could not be updated.")
        return _memory_view(memory)
    finally:
        database.close()


@app.delete("/memories/{memory_id}")
def delete_memory_endpoint(memory_id: str) -> dict[str, Any]:
    database = _db()
    try:
        deleted = database.delete_memory(memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found or could not be deleted.")
        return {"success": True, "deleted_id": memory_id, "message": "Memory deleted successfully."}
    finally:
        database.close()


@app.get("/memory/graph")
def memory_graph(limit: int = Query(default=250, ge=1, le=500)) -> dict[str, Any]:
    database = _db()
    try:
        return database.get_graph(limit)
    finally:
        database.close()


@app.get("/memory/{kind}")
def memory_kind(kind: str, limit: int = Query(default=100, ge=1, le=250)) -> dict[str, Any]:
    if kind.lower() not in {"episodic", "semantic", "temporary", "procedural"}:
        raise HTTPException(status_code=404, detail="Unknown memory category.")
    return memories(type=kind, limit=limit)


@app.get("/conversations")
def list_conversations(user_id: str = "default_user", limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
    database = _db()
    try:
        items = database.get_conversations(user_id=user_id, limit=limit)
        return {"items": items, "count": len(items)}
    finally:
        database.close()


@app.post("/conversations")
def create_conversation_endpoint(payload: ConversationCreate) -> dict[str, Any]:
    database = _db()
    try:
        cid = database.create_conversation(title=payload.title, user_id=payload.user_id)
        return {"conversation_id": cid, "title": payload.title, "user_id": payload.user_id}
    finally:
        database.close()


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, limit: int = Query(default=100, ge=1, le=250)) -> dict[str, Any]:
    database = _db()
    try:
        msgs = database.get_messages(conversation_id, limit=limit)
        return {"items": msgs, "count": len(msgs)}
    finally:
        database.close()


@app.get("/processing/logs")
def get_processing_audit_logs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    database = _db()
    try:
        logs = database.get_processing_logs(limit=limit)
        return {"items": logs, "count": len(logs)}
    finally:
        database.close()


@app.get("/projects")
def projects() -> dict[str, Any]:
    database = _db()
    try:
        records = database.get_collection_documents("projects")
        return {"items": records, "count": len(records)}
    finally:
        database.close()


@app.post("/projects", status_code=201)
def create_project(payload: DocumentCreate) -> dict[str, Any]:
    database = _db()
    try:
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        pid = database.insert_collection_document("projects", data)
        return {"id": pid, "status": "created", "collection": "projects", **data}
    finally:
        database.close()


@app.get("/documents")
def documents() -> dict[str, Any]:
    database = _db()
    try:
        records = database.get_collection_documents("documents")
        return {"items": records, "count": len(records)}
    finally:
        database.close()


@app.post("/documents", status_code=201)
def create_document(payload: DocumentCreate) -> dict[str, Any]:
    database = _db()
    try:
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        did = database.insert_collection_document("documents", data)
        return {"id": did, "status": "created", "collection": "documents", **data}
    finally:
        database.close()


@app.get("/analytics")
def analytics() -> dict[str, Any]:
    database = _db()
    try:
        return database.get_memory_statistics()
    finally:
        database.close()


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static_root")

