"""IND 2026 salary thresholds (gross/month excl. holiday allowance). Source: ind.nl required-amounts page, checked 2026-11-18."""
SOURCE = "https://ind.nl/en/required-amounts-income-requirements"
CHECKED = "2026-11-18"
VALID_TO = "2026-12-31"  # HSM amounts change every 1 January
THRESHOLDS = {
    "hsm_under30": 4357.0, "hsm_30plus": 5942.0, "hsm_reduced": 3122.0,
    "blue_card": 5942.0, "blue_card_reduced": 4754.0, "internship": 1168.5, "other": 2337.0,
}
def monthly(lo, hi, period):
    v = lo if lo else hi
    if not v: return None
    if period == "year": return v / 12.96
    if period == "month": return v / 1.08
    if period == "hour": return v * 165 / 1.08
    return None
def verdict(lo, hi, period, category):
    t = THRESHOLDS.get(category)
    m = monthly(lo, hi, period)
    if t is None or m is None:
        return {"verdict": "unknown", "threshold": t, "monthly": None}
    return {"verdict": "meets" if m >= t else "below", "threshold": t, "monthly": round(m), "margin": round(m - t),
            "source": SOURCE, "checked": CHECKED}
