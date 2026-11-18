import re, datetime as dt
from email.utils import parsedate_to_datetime
def norm_date(v):
    """epoch(s/ms), ISO, RFC822, 'Posted 3 Days Ago' -> 'YYYY-MM-DD' or None"""
    if v in (None, "", 0): return None
    try:
        if isinstance(v, (int, float)) or re.fullmatch(r"\d{9,13}", str(v)):
            x = float(v); x = x / 1000 if x > 1e11 else x
            return dt.datetime.fromtimestamp(x, dt.timezone.utc).date().isoformat()
        s = str(v).strip()
        m = re.search(r"(\d+)\+?\s*days?\s*ago", s, re.I)
        if m: return (dt.date.today() - dt.timedelta(days=int(m.group(1)))).isoformat()
        if re.search(r"today|just now", s, re.I): return dt.date.today().isoformat()
        if re.search(r"yesterday", s, re.I): return (dt.date.today() - dt.timedelta(days=1)).isoformat()
        m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
        if m: return m.group(1)
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return None
