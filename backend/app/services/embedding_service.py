"""Local sentence embeddings (fastembed / ONNX, no API key, no GPU). Lazy singleton; encodes job posting text and search queries into the same 384-d space."""
import threading
from app.core.config import settings

_model, _lk = None, threading.Lock()


def available() -> bool:
    if not settings.semantic_enabled: return False
    try:
        import fastembed  # noqa
        return True
    except Exception: return False


def _get():
    global _model
    with _lk:
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(model_name=settings.embedding_model)
        return _model


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _get().embed([t[:2000] for t in texts])]


def embed_query(q: str) -> list[float]:
    m = _get()
    return next(iter(m.query_embed([q[:500]]))).tolist() if hasattr(m, "query_embed") else embed([q])[0]


def job_text(title: str, company: str, location: str | None, description: str | None) -> str:
    return f"{title}. {company}. {location or ''}. {(description or '')[:1200]}"
