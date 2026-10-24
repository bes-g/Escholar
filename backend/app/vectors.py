"""Chunk published scholarship text and store embeddings locally and, when configured, in Pinecone."""

import logging
import math
import os
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChunkSetting, Scholarship, ScholarshipChunk
from app.record import vector_documents

logger = logging.getLogger("escholar")
NAMESPACE = "scholarships"


class VectorError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_chunk_sizes(small: int, large: int, overlap: int) -> list[str]:
    errors = []
    if small < 80 or small > 2000:
        errors.append("Small chunk size must be between 80 and 2000 characters.")
    if large < 200 or large > 8000:
        errors.append("Large chunk size must be between 200 and 8000 characters.")
    if large <= small:
        errors.append("Large chunks must be bigger than small chunks.")
    if overlap < 0 or overlap >= small:
        errors.append("Overlap must be zero or more, and smaller than the small chunk.")
    return errors


def get_chunk_settings(db: Session) -> ChunkSetting:
    row = db.get(ChunkSetting, 1)
    if row is None:
        row = ChunkSetting(
            id=1,
            small_chunk_size=400,
            large_chunk_size=1200,
            chunk_overlap=80,
            last_error="",
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.flush()
    return row


def windows(text: str, size: int, overlap: int) -> list[str]:
    compact = " ".join((text or "").split())
    if not compact:
        return []
    if len(compact) <= size:
        return [compact]
    step = max(1, size - overlap)
    pieces = []
    start = 0
    while start < len(compact):
        piece = compact[start : start + size].strip()
        if piece:
            pieces.append(piece)
        if start + size >= len(compact):
            break
        start += step
    return pieces


def split_chunks(text: str, small: int, large: int, overlap: int) -> list[dict]:
    chunks = []
    for index, big in enumerate(windows(text, large, overlap)):
        parent_key = f"large-{index}"
        chunks.append({"kind": "large", "parent_key": None, "position": index, "text": big})
        for child_index, piece in enumerate(windows(big, small, overlap)):
            chunks.append(
                {
                    "kind": "small",
                    "parent_key": parent_key,
                    "position": child_index,
                    "text": piece,
                }
            )
    return chunks


def document_text(row: Scholarship) -> str:
    criteria = row.criteria or []
    labels = [str(rule.get("label") or "") for rule in criteria if isinstance(rule, dict)]
    documents = [str(item) for item in (row.required_documents or [])]
    parts = [
        row.name,
        row.provider,
        f"Deadline {row.deadline}",
        row.summary,
        row.eligibility_notes or "",
        row.excerpt or "",
        " ".join(labels),
        " ".join(documents),
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())[:20000]


def embed_texts(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise VectorError("Embeddings are not called during tests.")
    if not texts:
        return []
    if not settings.llm_api_key.strip():
        raise VectorError("No model API key, so embeddings were not saved.")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.embedding_model}:batchEmbedContents"
    )
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 16):
        batch = texts[start : start + 16]
        payload = {
            "requests": [
                {
                    "model": f"models/{settings.embedding_model}",
                    "content": {"parts": [{"text": text[:8000]}]},
                    "taskType": task,
                    "outputDimensionality": settings.embedding_dimensions,
                }
                for text in batch
            ]
        }
        try:
            response = httpx.post(url, headers={"x-goog-api-key": settings.llm_api_key.strip()}, json=payload, timeout=30)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            raise VectorError(f"The embedding service returned {exc.response.status_code}.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise VectorError("The embedding service did not return vectors.") from exc
        rows = body.get("embeddings") or []
        if len(rows) != len(batch):
            raise VectorError("The embedding service returned an unexpected number of vectors.")
        for row in rows:
            values = row.get("values") or []
            if not values:
                raise VectorError("The embedding service returned an empty vector.")
            vectors.append([float(value) for value in values])
    return vectors


def _pinecone_index():
    if not settings.pinecone_api_key.strip():
        return None
    from pinecone import Pinecone

    client = Pinecone(api_key=settings.pinecone_api_key.strip())
    return client.Index(settings.pinecone_index.strip() or "escholar")


def _upsert_pinecone(chunks: list[ScholarshipChunk]) -> str:
    ready = [chunk for chunk in chunks if chunk.embedding]
    if not ready:
        return "local"
    if not settings.pinecone_api_key.strip():
        return "local"
    try:
        index = _pinecone_index()
        vectors = [
            {
                "id": chunk.vector_id,
                "values": chunk.embedding,
                "metadata": {
                    "scholarship_id": chunk.scholarship_id,
                    "kind": chunk.kind,
                    "chunk_id": chunk.id,
                    "section": chunk.section or "",
                },
            }
            for chunk in ready
        ]
        for start in range(0, len(vectors), 100):
            index.upsert(vectors=vectors[start : start + 100], namespace=NAMESPACE)
    except Exception as exc:
        logger.warning("Pinecone upsert failed: %s", exc.__class__.__name__)
        return f"local (Pinecone was not updated: {exc.__class__.__name__})"
    return "pinecone"


def drop_scholarship(db: Session, scholarship_id: str) -> None:
    rows = db.query(ScholarshipChunk).filter(ScholarshipChunk.scholarship_id == scholarship_id).all()
    ids = [row.vector_id for row in rows if row.vector_id]
    if ids and settings.pinecone_api_key.strip():
        try:
            _pinecone_index().delete(ids=ids, namespace=NAMESPACE)
        except Exception as exc:
            logger.warning("Pinecone delete failed: %s", exc.__class__.__name__)
    for row in rows:
        db.delete(row)


def index_scholarship(db: Session, row: Scholarship) -> dict:
    settings_row = get_chunk_settings(db)
    drop_scholarship(db, row.id)
    db.flush()
    pieces = []
    for document in vector_documents(
        row.name,
        row.provider,
        row.source_url or "",
        row.summary,
        row.deadline,
        row.eligibility_notes or "",
        list(row.required_documents or []),
        list(row.criteria or []),
        row.sections or {},
    ):
        for piece in split_chunks(
            document["text"],
            settings_row.small_chunk_size,
            settings_row.large_chunk_size,
            settings_row.chunk_overlap,
        ):
            if piece["kind"] == "large":
                piece["slot"] = f"{document['section']}-large-{piece['position']}"
                piece["parent_key"] = None
            elif piece["parent_key"]:
                piece["parent_key"] = f"{document['section']}-{piece['parent_key']}"
            piece["section"] = document["section"]
            pieces.append(piece)
    if not pieces:
        settings_row.last_error = "That scholarship has no text to embed."
        return {"chunks": 0, "embedded": 0, "store": "local"}

    now = datetime.now(timezone.utc)
    parents: dict[str, ScholarshipChunk] = {}
    stored: list[ScholarshipChunk] = []
    parent_keys: list[str | None] = []
    for piece in pieces:
        chunk = ScholarshipChunk(
            id=f"chk_{uuid4().hex[:12]}",
            scholarship_id=row.id,
            kind=piece["kind"],
            parent_id=None,
            position=piece["position"],
            text=piece["text"],
            char_count=len(piece["text"]),
            embedding=None,
            vector_id="",
            section=piece.get("section") or "",
            created_at=now,
        )
        if piece["kind"] == "large":
            parents[piece["slot"]] = chunk
        parent_keys.append(piece["parent_key"])
        stored.append(chunk)
        db.add(chunk)
    for chunk, parent_key in zip(stored, parent_keys):
        if parent_key and parent_key in parents:
            chunk.parent_id = parents[parent_key].id
    db.flush()

    try:
        vectors = embed_texts([chunk.text for chunk in stored], task="RETRIEVAL_DOCUMENT")
    except VectorError as exc:
        settings_row.last_error = exc.message
        return {"chunks": len(stored), "embedded": 0, "store": "local"}

    for chunk, vector in zip(stored, vectors):
        chunk.embedding = vector
        chunk.vector_id = chunk.id
    settings_row.last_error = ""
    store = _upsert_pinecone(stored)
    if store.startswith("local ("):
        settings_row.last_error = store
    return {"chunks": len(stored), "embedded": len(vectors), "store": store}


def reindex_published(db: Session) -> dict:
    rows = db.query(Scholarship).filter(Scholarship.status == "published").all()
    totals = {"scholarships": 0, "chunks": 0, "embedded": 0, "store": "local"}
    for row in rows:
        result = index_scholarship(db, row)
        totals["scholarships"] += 1
        totals["chunks"] += result["chunks"]
        totals["embedded"] += result["embedded"]
        totals["store"] = result["store"]
    return totals


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def profile_text(profile: dict) -> str:
    parts = [
        profile.get("student_name") or "",
        profile.get("student_level") or "",
        profile.get("degree_level") or "",
        profile.get("field_of_study") or "",
        profile.get("prior_field") or "",
        profile.get("institution") or "",
        profile.get("stream") or "",
        f"grade {profile.get('grade_level')}" if profile.get("grade_level") else "",
        f"year {profile.get('year_of_study')}" if profile.get("year_of_study") else "",
        f"GPA {profile.get('gpa')}" if profile.get("gpa") is not None else "",
        profile.get("country") or "",
        profile.get("citizenship") or "",
        profile.get("research_interest") or "",
    ]
    return " ".join(str(part) for part in parts if part)


def similar_chunks(db: Session, profile: dict, limit: int = 6) -> list[dict]:
    rows = db.query(ScholarshipChunk).filter(ScholarshipChunk.embedding.isnot(None)).all()
    if not rows:
        return []
    query = embed_texts([profile_text(profile)], task="RETRIEVAL_QUERY")[0]
    ranked = []
    remote = _query_pinecone(query, limit)
    if remote is not None:
        by_id = {row.id: row for row in rows}
        for item in remote:
            row = by_id.get(item["id"])
            if row is not None:
                ranked.append((item["score"], row))
    else:
        ranked = sorted(((cosine(query, row.embedding), row) for row in rows), key=lambda item: item[0], reverse=True)
    hits = []
    seen = set()
    for score, row in ranked:
        if score < settings.match_similarity or row.scholarship_id in seen:
            continue
        seen.add(row.scholarship_id)
        parent = db.get(ScholarshipChunk, row.parent_id) if row.parent_id else None
        passage = parent.text if parent is not None else row.text
        hits.append(
            {
                "scholarship_id": row.scholarship_id,
                "chunk_id": row.id,
                "kind": row.kind,
                "score": round(float(score), 4),
                "passage": passage[:500],
            }
        )
        if len(hits) >= limit:
            break
    return hits


def _query_pinecone(vector: list[float], limit: int) -> list[dict] | None:
    if not settings.pinecone_api_key.strip():
        return None
    try:
        result = _pinecone_index().query(vector=vector, top_k=max(limit * 3, 8), namespace=NAMESPACE, include_metadata=True)
    except Exception as exc:
        logger.warning("Pinecone query failed: %s", exc.__class__.__name__)
        return None
    matches = getattr(result, "matches", None) or result.get("matches", [])
    hits = []
    for match in matches:
        if isinstance(match, dict):
            hits.append({"id": match.get("id"), "score": match.get("score") or 0})
        else:
            hits.append({"id": match.id, "score": match.score or 0})
    return hits
