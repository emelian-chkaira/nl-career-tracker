"""Layout-aware PDF -> normalised CV text.

Keeps what a flat text dump loses:
 * hyperlinks  - PDF link annotations are mapped onto the characters they cover and emitted as ``[label](url)``;
 * columns     - a left title and a right-aligned date/location are separate segments, always read left to right (joined by two spaces);
 * bold / caps - bold entry titles, bold labels and upper-case section headings are recognised;
 * running page footers and page numbers are removed (the footer text is returned separately).

Markers understood by cv.py: '\\x01' = row starts with a bold segment (entry title / skill label), '\\x02' = unknown section heading."""
import io, re, statistics
from collections import Counter
from . import cv as cvmod

BULLET = re.compile(r"^\s*[•●▪◦‣∙·◆■►➢–\-\*]\s+")
BOLD = re.compile(r"bold|black|heavy|semibold|demi|-bd\b|bd$|extrabold", re.I)
FOOTER = re.compile(r"^.{3,60}?\s[-–—|]\s*(curriculum vitae|resume|résumé|cv)\b.*$", re.I)


class _Sp:
    def get_text(self): return " "


def _col(c):
    try: return str(c.graphicstate.ncolor)
    except Exception: return ""


def _links(reader_pages) -> dict[int, list]:
    out = {}
    for pno, page in enumerate(reader_pages):
        rects = []
        for a in page.get("/Annots") or []:
            try:
                a = a.get_object(); act = a.get("/A")
                uri = (act.get_object().get("/URI") if act else None)
                if uri and a.get("/Rect"): r = [float(x) for x in a["/Rect"]]; rects.append((min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3]), str(uri)))
            except Exception: continue
        out[pno] = rects
    return out


def _url_at(rects, x, y):
    for x0, y0, x1, y1, u in rects:
        if x0 - 1 <= x <= x1 + 1 and y0 - 2 <= y <= y1 + 2: return u
    return None


def _bold_wrap(items):
    """items [(char, url, bold)] -> [(char, url)] with **..** around inline bold runs (only when the segment is mostly regular text)."""
    flags = [b for ch, u, b in items if ch.strip()]
    if not flags or sum(flags) >= 0.6 * len(flags) or not any(flags): return [(ch, u) for ch, u, _ in items]
    out, i, n = [], 0, len(items)
    while i < n:
        ch, u, b = items[i]
        if not (b and ch.strip()): out.append((ch, u)); i += 1; continue
        j = i
        while j < n and (items[j][2] or (items[j][0] == " " and j + 1 < n and items[j + 1][2])): j += 1
        run = items[i:j]
        out += [("**", None)] + [(c, uu) for c, uu, _ in run] + [("**", None)]; i = j
    return out


def _markup(items):
    """[(char, url|None)] -> text with [label](url) for linked runs (a space between two chars of one link belongs to the link)."""
    out, i, n = [], 0, len(items)
    while i < n:
        ch, u = items[i]
        if u is None: out.append(ch); i += 1; continue
        j, buf = i, []
        while j < n:
            c2, u2 = items[j]
            if u2 == u: buf.append(c2); j += 1
            elif c2 == " " and j + 1 < n and items[j + 1][1] == u: buf.append(c2); j += 1
            else: break
        label = "".join(buf).strip()
        lead = len("".join(buf)) - len("".join(buf).lstrip())
        out.append(" " * lead + (f"[{label}]({u})" if label and not u.startswith("mailto:") and not u.startswith("tel:") else label))
        i = j
    return "".join(out)


def rows_of(data: bytes) -> list[dict]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextContainer, LTTextLine, LTChar
    from pypdf import PdfReader
    try: links = _links(PdfReader(io.BytesIO(data)).pages)
    except Exception: links = {}
    segs = []
    for pno, page in enumerate(extract_pages(io.BytesIO(data), laparams=LAParams(line_margin=0.35, boxes_flow=None), maxpages=8)):
        rects = links.get(pno, [])
        for box in page:
            if not isinstance(box, LTTextContainer): continue
            for ln in box:
                if not isinstance(ln, LTTextLine): continue
                cur, last = [], None
                def close():
                    nonlocal cur
                    chars = [c for c, _ in cur if isinstance(c, LTChar)]
                    if chars:
                        txt = _markup(_bold_wrap([(c.get_text(), u, bool(isinstance(c, LTChar) and BOLD.search(c.fontname or ""))) for c, u in cur])).strip()
                        if txt: segs.append({"page": pno, "text": txt, "x0": min(c.x0 for c in chars), "x1": max(c.x1 for c in chars), "y0": min(c.y0 for c in chars), "size": statistics.median(c.size for c in chars),
                                             "bold": sum(1 for c in chars if BOLD.search(c.fontname or "")) >= 0.6 * len(chars), "raw": "".join(c.get_text() for c, _ in cur).strip()})
                    cur = []
                for c in ln:
                    if not isinstance(c, LTChar):
                        if cur and c.get_text() == " ": cur.append((c, None))
                        continue
                    if last is not None and c.x0 - last.x1 > max(14, 2.6 * c.size): close()
                    elif last is not None and cur and all(isinstance(k, LTChar) and BOLD.search(k.fontname or "") for k, _ in cur if isinstance(k, LTChar)) \
                            and not BOLD.search(c.fontname or "") and c.x0 - last.x1 > 0.9 * c.size: close()      # bold label | normal text column
                    elif last is not None and c.x0 - last.x1 > 0.9 * c.size and _col(c) != _col(last): close()                   # grey meta vs accent link vs black text
                    elif last is not None and cur and c.x0 - last.x1 > 0.18 * c.size and cur[-1][0].get_text() != " ": cur.append((_Sp(), None))   # letter-spaced caps lose their spaces
                    cur.append((c, _url_at(rects, (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2))); last = c
                close()
    # segments sharing a baseline form one visual row, read left to right; touching segments are one run of text
    segs.sort(key=lambda s: (s["page"], -round(s["y0"] / 3), s["x0"]))
    rows = []
    for s in segs:
        if rows and rows[-1]["page"] == s["page"] and abs(rows[-1]["y0"] - s["y0"]) < 3.5: rows[-1]["segs"].append(s)
        else: rows.append({"page": s["page"], "y0": s["y0"], "segs": [s]})
    for r in rows:
        r["segs"].sort(key=lambda s: s["x0"]); merged = [r["segs"][0]]
        for s in r["segs"][1:]:
            p = merged[-1]
            if s["x0"] - p["x1"] <= max(14, 2.6 * s["size"]) and s["bold"] == p["bold"]:
                p["text"] += (" " if s["x0"] - p["x1"] > 1 else "") + s["text"]; p["raw"] += " " + s["raw"]; p["x1"] = s["x1"]
            else: merged.append(s)
        r["segs"] = merged; r["x"] = merged[0]["x0"]; r["size"] = max(s["size"] for s in merged)
    return rows


def pdf_to_text(data: bytes) -> str:
    return pdf_to_doc(data)["text"]


def pdf_to_doc(data: bytes) -> dict:
    rows = rows_of(data)
    if not rows: return {"text": "", "footer": ""}
    body = Counter()
    for r in rows:
        for s in r["segs"]: body[round(s["size"], 1)] += len(s["raw"])
    body_size = body.most_common(1)[0][0]
    left = min(r["x"] for r in rows)
    out, footer = [], ""
    for r in rows:
        text = "  ".join(s["text"] for s in r["segs"]).replace("–", "-").replace("—", "-")
        text = re.sub(r"^\s*\(cid:\d+\)\s*", "• ", text)
        core = text.strip(); plain = "  ".join(s["raw"] for s in r["segs"]).strip()
        if re.fullmatch(r"\d{1,2}", plain): continue                                   # page number
        if FOOTER.match(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", core)) and len(r["segs"]) <= 2: footer = footer or core; continue
        if BULLET.match(core): out.append("- " + BULLET.sub("", core)); continue
        words = plain.split(); single = len(r["segs"]) == 1
        if any(h.match(plain.strip(": ")) for h in cvmod.HEAD_RE.values()): out += ["", plain.strip(": "), ""]
        elif (single and 1 <= len(words) <= 5 and len(plain) < 46 and r["x"] <= left + 6 and not re.search(r"[\d@|,.]", plain) and out
              and ((r["segs"][0]["bold"] and plain.upper() == plain) or r["size"] >= body_size * 1.1 and (plain.upper() == plain or r["segs"][0]["bold"]))):
            out += ["", "\x02" + plain, ""]                                           # unknown section heading: bold + ALL CAPS (or larger)
        elif r["segs"][0]["bold"]: out.append("\x01" + text)                          # bold title / label first
        else: out.append(text)
    return {"text": re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip(), "footer": footer}
