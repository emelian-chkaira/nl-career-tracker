import re
_SUFFIX = re.compile(r"\b(b\.?v\.?|n\.?v\.?|holding|group|nederland|netherlands|the netherlands|international|europe|v\.?o\.?f\.?|c\.?v\.?|ltd|limited|inc|gmbh|llc)\b", re.I)
def norm(s: str) -> str:
    """Company-name normalisation shared by the sponsor matcher and the crawler."""
    s = (s or "").lower().replace("&", " and ")
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
