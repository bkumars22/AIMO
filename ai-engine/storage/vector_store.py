"""
pgvector operations — embedding storage and cosine similarity search.

Phase 1: implement using pgvector Python client + SQLAlchemy.
"""
from __future__ import annotations

EMBED_MODEL = "all-MiniLM-L6-v2"   # 384-dim, loaded once at startup
_model = None                        # lazy-loaded sentence-transformers model


def get_embed_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed(text: str) -> list[float]:
    """Embed text with all-MiniLM-L6-v2. Returns 384-dim vector."""
    model = get_embed_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def store_response_embedding(
    pipeline_id: str,
    run_id: str,
    node_name: str,
    text: str,
    label: str,
    input_hash: str | None = None,
) -> None:
    """Store a response embedding in response_embeddings table."""
    raise NotImplementedError("Phase 1")


def search_compliant_baselines(pipeline_id: str, embedding: list[float], top_k: int = 5) -> list[float]:
    """
    Cosine similarity search against compliant baseline embeddings.
    Returns list of similarity scores.
    """
    raise NotImplementedError("Phase 1")


def search_injection_vectors(embedding: list[float], top_k: int = 3) -> list[tuple[float, str]]:
    """
    Cosine similarity search against known injection vectors.
    Returns list of (similarity_score, injection_type).
    """
    raise NotImplementedError("Phase 1")


def seed_injection_vectors(golden_dataset_path: str) -> int:
    """
    Seed injection_vectors table from golden_dataset.json adversarial cases.
    Called once at startup. Returns number of vectors inserted.
    """
    raise NotImplementedError("Phase 1")
