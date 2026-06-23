"""
voice/tools/memory_tool.py
--------------------------
Two-layer memory:
  1. ChromaDB  — semantic / fuzzy search over long-form memories
  2. SQLite    — structured key facts + scheduled reminders
"""
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite
import chromadb
from chromadb.utils import embedding_functions
from loguru import logger

from voice.config import settings


# ── ChromaDB (semantic memory) ────────────────────────────────────────────────

_chroma_client: chromadb.ClientAPI | None = None
_collection = None


def _get_chroma():
    global _chroma_client, _collection
    if _chroma_client is None:
        Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        ef = embedding_functions.DefaultEmbeddingFunction()
        _collection = _chroma_client.get_or_create_collection(
            name="friday_memories",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB ready — {_collection.count()} memories loaded")
    return _collection


def store_memory(text: str, metadata: dict | None = None) -> str:
    col = _get_chroma()
    mem_id = str(uuid.uuid4())
    meta = {"created_at": datetime.utcnow().isoformat(), **(metadata or {})}
    col.add(documents=[text], metadatas=[meta], ids=[mem_id])
    logger.info(f"Memory stored: {text[:60]}...")
    return mem_id


def search_memories(query: str, n_results: int | None = None) -> list[dict]:
    col = _get_chroma()
    k = n_results or settings.memory_top_k
    count = col.count()
    if count == 0:
        return []
    results = col.query(query_texts=[query], n_results=min(k, count))
    return [
        {"text": doc, "metadata": meta}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


# ── SQLite (structured facts + reminders) ─────────────────────────────────────

async def _get_db() -> aiosqlite.Connection:
    Path(settings.facts_db_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.facts_db_path)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reminders (
            id         TEXT PRIMARY KEY,
            message    TEXT NOT NULL,
            fire_at    TEXT NOT NULL,
            sent       INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    await db.commit()
    return db


async def set_fact(key: str, value: str) -> None:
    db = await _get_db()
    async with db:
        await db.execute(
            "INSERT OR REPLACE INTO facts (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_fact(key: str) -> str | None:
    db = await _get_db()
    async with db:
        async with db.execute("SELECT value FROM facts WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def add_reminder(message: str, fire_at: datetime) -> str:
    rem_id = str(uuid.uuid4())
    db = await _get_db()
    async with db:
        await db.execute(
            "INSERT INTO scheduled_reminders (id, message, fire_at, created_at) VALUES (?, ?, ?, ?)",
            (rem_id, message, fire_at.isoformat(), datetime.utcnow().isoformat()),
        )
        await db.commit()
    return rem_id


async def get_pending_reminders(before: datetime) -> list[dict]:
    db = await _get_db()
    async with db:
        async with db.execute(
            "SELECT id, message, fire_at FROM scheduled_reminders WHERE sent = 0 AND fire_at <= ?",
            (before.isoformat(),),
        ) as cur:
            rows = await cur.fetchall()
            return [{"id": r[0], "message": r[1], "fire_at": r[2]} for r in rows]


async def mark_reminder_sent(rem_id: str) -> None:
    db = await _get_db()
    async with db:
        await db.execute("UPDATE scheduled_reminders SET sent = 1 WHERE id = ?", (rem_id,))
        await db.commit()


# ── Tool handlers ─────────────────────────────────────────────────────────────

async def tool_remember(text: str, key: str | None = None) -> str:
    store_memory(text)
    if key:
        await set_fact(key, text)
    return "Got it, I'll remember that."


async def tool_recall(query: str) -> str:
    results = search_memories(query, n_results=5)
    if not results:
        return "I don't have anything stored about that."
    lines = [r["text"] for r in results]
    return "Here's what I remember: " + ". ".join(lines)
