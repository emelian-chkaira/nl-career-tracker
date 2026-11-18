"""In-process sliding-window limiter (per key). For multi-instance deployments swap `allow` for a Redis-backed one — the interface stays the same."""
import time, threading
_hits: dict[str, list[float]] = {}
_lk = threading.Lock()


def allow(key: str, limit: int, window: float = 60.0) -> bool:
    if not limit: return True
    now = time.time()
    with _lk:
        h = [t for t in _hits.get(key, []) if now - t < window]
        ok = len(h) < limit
        if ok: h.append(now)
        _hits[key] = h
        if len(_hits) > 20000:
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > window]: _hits.pop(k, None)
        return ok


def reset(): _hits.clear()
