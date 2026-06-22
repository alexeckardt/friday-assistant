"""
memory/store.py
---------------
Two-layer memory:
  1. ChromaDB  — semantic / fuzzy search over long-form memories
  2. SQLite    — structured key facts (name, preferences, etc.)
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite
import chromadb
from chromadb.utils import embedding_functions
from loguru import logger

from config.settings import settings


# ── ChromaDB (semantic memory) ───────────────────────────────────────────────

_chroma_client: chromadb.ClientAPI | None = None
_collection = None


def _get_chroma():
    global _chroma_client, _collection
    if _chroma_client is None:
        Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        ef = embedding_functions.DefaultEmbeddingFunction()
        _collection = _chroma_client.get_or_create_collection(
            name="jarvis_memories",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB ready — {_collection.count()} memories loaded")
    return _collection


def store_memory(text: str, metadata: dict | None = None) -> str:
    """Store a memory and return its ID."""
    col = _get_chroma()
    mem_id = str(uuid.uuid4())
    meta = {
        "created_at": datetime.utcnow().isoformat(),
        **(metadata or {}),
    }
    col.add(documents=[text], metadatas=[meta], ids=[mem_id])
    logger.info(f"Memory stored: {text[:60]}...")
    return mem_id


def search_memories(query: str, n_results: int | None = None) -> list[dict]:
    """Return top-k relevant memories for a query."""
    col = _get_chroma()
    k = n_results or settings.memory_top_k
    count = col.count()
    if count == 0:
        return []
    results = col.query(query_texts=[query], n_results=min(k, count))
    memories = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        memories.append({"text": doc, "metadata": meta})
    return memories


def delete_memory(mem_id: str) -> bool:
    col = _get_chroma()
    try:
        col.delete(ids=[mem_id])
        return True
    except Exception as e:
        logger.warning(f"Could not delete memory {mem_id}: {e}")
        return False


# ── SQLite (structured facts) ────────────────────────────────────────────────

async def _get_db() -> aiosqlite.Connection:
    Path(settings.facts_db_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.facts_db_path)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
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
    logger.info(f"Fact set: {key} = {value}")


async def get_fact(key: str) -> str | None:
    db = await _get_db()
    async with db:
        async with db.execute("SELECT value FROM facts WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_all_facts() -> dict[str, str]:
    db = await _get_db()
    async with db:
        async with db.execute("SELECT key, value FROM facts") as cur:
            rows = await cur.fetchall()
            return {row[0]: row[1] for row in rows}


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
        await db.execute(
            "UPDATE scheduled_reminders SET sent = 1 WHERE id = ?", (rem_id,)
        )
        await db.commit()
