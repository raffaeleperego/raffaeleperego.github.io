#!/usr/bin/env python3
"""Build the publication list from a DBLP BibTeX export.

Update workflow:
  1. Download BibTeX from https://dblp.org/pid/p/RaffaelePerego.html
     (export icon -> BibTeX) and save it as data/dblp.bib
  2. python3 scripts/build_publications.py
  3. Upload / push the site.

Classification rules live in data/venues.yml, topic tagging in
data/topics.yml, hand fixes (drop, retype, highlight) in
data/overrides.yml. Outputs:
  data/publications.json           canonical dump
  assets/js/publications-data.js   window.PUBLICATIONS for the page
                                   (a script, so the site also works
                                   opened from disk and on any host)

No dependencies beyond the standard library and PyYAML.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BIB = ROOT / "data" / "dblp.bib"
VENUES = ROOT / "data" / "venues.yml"
TOPICS = ROOT / "data" / "topics.yml"
OVERRIDES = ROOT / "data" / "overrides.yml"
OUT_JSON = ROOT / "data" / "publications.json"
OUT_JS = ROOT / "assets" / "js" / "publications-data.js"
SITEMAP = ROOT / "sitemap.xml"

ME = "Raffaele Perego"


# --------------------------------------------------------------------------
# BibTeX parsing (DBLP output is regular enough for a small brace parser)
# --------------------------------------------------------------------------

def parse_bibtex(text: str) -> list[dict]:
    entries = []
    i, n = 0, len(text)
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text[at:])
        if not m:
            i = at + 1
            continue
        etype, key = m.group(1).lower(), m.group(2)
        j = at + m.end()
        fields: dict[str, str] = {}
        while j < n:
            while j < n and text[j] in " \t\r\n,":
                j += 1
            if j < n and text[j] == "}":
                j += 1
                break
            fm = re.match(r"([\w-]+)\s*=\s*", text[j:])
            if not fm:
                j += 1
                continue
            name = fm.group(1).lower()
            j += fm.end()
            if text[j] == "{":
                depth, k = 0, j
                while k < n:
                    c = text[k]
                    if c == "\\":
                        k += 2
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                value = text[j + 1:k]
                j = k + 1
            elif text[j] == '"':
                k = text.index('"', j + 1)
                value = text[j + 1:k]
                j = k + 1
            else:
                vm = re.match(r"[^,}\s]+", text[j:])
                value = vm.group(0)
                j += vm.end()
            fields[name] = value
        entries.append({"type": etype, "key": key, **fields})
        i = j
    return entries


LATEX_ACCENTS = {
    "'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
    "c": "\u0327", "v": "\u030c", "u": "\u0306", "=": "\u0304", ".": "\u0307",
    "H": "\u030b", "k": "\u0328", "r": "\u030a",
}
LATEX_SYMBOLS = {
    r"\o": "ø", r"\O": "Ø", r"\ss": "ß", r"\l": "ł", r"\L": "Ł",
    r"\aa": "å", r"\AA": "Å", r"\ae": "æ", r"\AE": "Æ", r"\i": "ı",
    r"\&": "&", r"\%": "%", r"\$": "$", r"\_": "_", r"\#": "#",
}


def delatex(s: str) -> str:
    def accent(m):
        base = m.group(2).replace("\\i", "i")
        return unicodedata.normalize("NFC", base + LATEX_ACCENTS[m.group(1)])
    s = re.sub(r"\{?\\([`'^\"~cvu=.Hkr])\s*\{?(\\i|[A-Za-z])\}?\}?", accent, s)
    for k, v in sorted(LATEX_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(re.escape(k) + r"(?![A-Za-z])\s?", v, s)
    s = s.replace("--", "–").replace("~", " ")
    s = re.sub(r"\\(emph|textit|textbf|mathrm|texttt)\s*", "", s)
    s = re.sub(r"\$([^$]*)\$", r"\1", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def clean_author(name: str) -> str:
    # DBLP disambiguates homonyms with a 4-digit suffix: "Paolo Ferragina 0001"
    return re.sub(r"\s+\d{4}$", "", delatex(name))


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def venue_of(key: str) -> tuple[str, str]:
    """('conf'|'journals'|..., venue id) from DBLP:conf/sigir/Foo15."""
    parts = key.split(":", 1)[-1].split("/")
    return (parts[0], parts[1].lower()) if len(parts) >= 2 else ("", "")


def classify(e: dict, venues: dict, ov: dict) -> str | None:
    kind, vid = venue_of(e["key"])
    title = e["title"].lower()
    for pat in venues.get("skip_title_patterns", []):
        if re.search(pat, e["title"], re.I):
            return None
    k = e["key"].removeprefix("DBLP:")
    if k in (ov.get("type") or {}):
        return ov["type"][k]
    if e["type"] == "proceedings":
        return "edited"
    if e["type"] in ("book", "incollection") or kind in ("books", "reference", "series"):
        return "book"
    if vid == "corr" or e.get("eprinttype", "").lower() == "arxiv" and e["type"] == "article":
        return "preprint"
    if kind == "data":
        return "other"
    if e["type"] == "article":
        if vid in venues["q1_journals"]:
            return "q1"
        # PVLDB is how VLDB papers appear; journals/sigir is SIGIR Forum, not the conference
        return "a_conf" if vid in venues["a_conferences"] and vid != "sigir" else "journal"
    if e["type"] == "inproceedings":
        bt = e.get("booktitle", "")
        if vid in venues.get("workshop_venues", []) or re.search(r"workshops?\b|@", bt, re.I):
            return "workshop"
        return "a_conf" if vid in venues["a_conferences"] else "conf"
    return "other"


def load_topics(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    topics = []
    for t in data["topics"]:
        topics.append({
            "slug": t["slug"], "label": t["label"],
            "re": [re.compile(p, re.I) for p in t.get("patterns", [])],
        })
    return topics


def tag_topics(text: str, topics: list[dict]) -> list[str]:
    tags = [t["slug"] for t in topics if any(r.search(text) for r in t["re"])]
    return tags or ["misc"]


def short_venue(e: dict, venues: dict) -> str:
    kind, vid = venue_of(e["key"])
    names = venues.get("display", {})
    if kind == "data":
        return "Dataset"
    if kind == "journals" and vid == "sigir":
        return "SIGIR Forum"
    if vid in names:
        return names[vid]
    if vid == "corr":
        return "arXiv"
    return vid.upper() if vid else ""


def full_venue(e: dict) -> str:
    v = e.get("booktitle") or e.get("journal") or e.get("series") or e.get("publisher") or ""
    return delatex(v)


# --------------------------------------------------------------------------
# Recent papers from OpenAlex (DBLP lags a few weeks/months behind)
# --------------------------------------------------------------------------

OPENALEX_AUTHOR = "A5035605298"
RECENT_YEARS = 2  # only look at the current and previous year


def make_recent(title, authors, year, ptype, venue, venue_full, url, key, topics, ov, selected):
    tags = tag_topics(f"{title} {venue_full}", topics)
    if len(tags) > 1 and "misc" in tags:
        tags.remove("misc")
    award = (ov.get("awards") or {}).get(key, "")
    return {"key": key, "title": title, "authors": authors, "year": year, "type": ptype,
            "venue": venue, "venue_full": venue_full, "url": url, "arxiv": "",
            "topics": tags, "selected": key in selected or bool(award), "award": award}


def fetch_openalex_recent(venues, topics, ov, selected) -> list[dict]:
    import urllib.parse
    import urllib.request
    since = f"{date.today().year - RECENT_YEARS + 1}-01-01"
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode({
        "filter": f"author.id:{OPENALEX_AUTHOR},from_publication_date:{since}",
        "per-page": 200,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "raffaele-homepage/1.0"})
    try:
        works = json.load(urllib.request.urlopen(req, timeout=60))["results"]
    except Exception as exc:  # network trouble must not break the build
        print(f"  warning: OpenAlex not reachable ({exc}); using DBLP only")
        return []
    patterns = [(re.compile(p, re.I), v) for p, v in (venues.get("openalex_venues") or {}).items()]
    out = []
    for w in works:
        title = clean_text(w.get("title") or "")
        if not title or any(re.search(p, title, re.I) for p in venues.get("skip_title_patterns", [])):
            continue
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        vid = next((v for rx, v in patterns if rx.search(src)), "")
        if w.get("type") == "preprint" or "arxiv" in src.lower():
            ptype, vid = "preprint", "corr"
        elif w.get("type") == "article":
            ptype = "q1" if vid in venues["q1_journals"] else "journal"
        elif w.get("type") == "conference-paper":
            ptype = "a_conf" if vid in venues["a_conferences"] else "conf"
        else:
            continue
        if not src:
            continue  # no venue at all: too unreliable to show
        authors = [a["author"]["display_name"] for a in w.get("authorships", [])]
        venue = venues.get("display", {}).get(vid, vid.upper()) if vid else ""
        out.append(make_recent(title, authors, int(w["publication_year"]), ptype, venue, src,
                               w.get("doi") or w["id"], "openalex:" + w["id"].rsplit("/", 1)[-1],
                               topics, ov, selected))
    return out


def clean_text(s: str) -> str:
    import html
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(s))).strip().rstrip(".")


def main() -> int:
    if not BIB.exists():
        sys.exit(f"missing {BIB}: download BibTeX from DBLP first")
    venues = yaml.safe_load(VENUES.read_text())
    venues["a_conferences"] = set(venues["a_conferences"])
    venues["q1_journals"] = set(venues["q1_journals"])
    topics = load_topics(TOPICS)
    ov = yaml.safe_load(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    ov = ov or {}
    drop = set(ov.get("drop", []) or [])
    selected = set(ov.get("selected", []) or [])
    extra_topics = ov.get("topics", {}) or {}

    raw = parse_bibtex(BIB.read_text(encoding="utf-8"))
    pubs, dropped = [], []
    for e in raw:
        if e["key"].removeprefix("DBLP:") in drop or "title" not in e:
            dropped.append(e["key"])
            continue
        e["title"] = delatex(e["title"]).rstrip(".")
        ptype = classify(e, venues, ov)
        if ptype is None:
            dropped.append(e["key"])
            continue
        authors = [clean_author(a) for a in re.split(r"\s+and\s+", e.get("author", "") or e.get("editor", "")) if a.strip()]
        doi = e.get("doi", "")
        url = f"https://doi.org/{doi}" if doi else e.get("url", "")
        if url.startswith("db/"):
            url = "https://dblp.org/" + url
        arxiv = e.get("eprint", "") if e.get("eprinttype", "").lower() == "arxiv" else ""
        venue = short_venue(e, venues)
        tags = tag_topics(f'{e["title"]} {full_venue(e)}', topics)
        k = e["key"].removeprefix("DBLP:")
        award = (ov.get("awards") or {}).get(k, "")
        if len(tags) > 1 and "misc" in tags:
            tags.remove("misc")
        pubs.append({
            "key": k,
            "title": e["title"],
            "authors": authors,
            "year": int(e.get("year", 0) or 0),
            "type": ptype,
            "venue": venue,
            "venue_full": full_venue(e),
            "url": url,
            "arxiv": arxiv,
            "topics": tags,
            "selected": k in selected or bool(award),
            "award": award,
        })

    def norm(t): return re.sub(r"[^a-z0-9]", "", t.lower())

    # Recent papers DBLP has not indexed yet: manual entries first, then OpenAlex.
    # A published version is added even when DBLP only has the arXiv preprint;
    # the preprint is folded into it below.
    known = {norm(p["title"]) for p in pubs}
    known_pub = {norm(p["title"]) for p in pubs if p["type"] != "preprint"}
    added = []
    for m in ov.get("extra", []) or []:
        if norm(m["title"]) in known_pub:
            print(f"  note: manual entry now in DBLP, remove it from overrides.yml: {m['title']}")
            continue
        vid = str(m.get("venue", "")).lower()
        ptype = m.get("type") or ("a_conf" if vid in venues["a_conferences"] else
                                  "q1" if vid in venues["q1_journals"] else "conf")
        p = make_recent(m["title"], m.get("authors", []), int(m["year"]), ptype,
                        venues.get("display", {}).get(vid, vid.upper()), m.get("venue_full", ""),
                        m.get("url", ""), "manual:" + norm(m["title"])[:40], topics, ov, selected)
        pubs.append(p); added.append(p); known.add(norm(p["title"])); known_pub.add(norm(p["title"]))
    if "--offline" not in sys.argv:
        for p in fetch_openalex_recent(venues, topics, ov, selected):
            seen = known if p["type"] == "preprint" else known_pub
            if norm(p["title"]) not in seen and p["key"].removeprefix("openalex:") not in drop:
                pubs.append(p); added.append(p); known.add(norm(p["title"]))
                if p["type"] != "preprint":
                    known_pub.add(norm(p["title"]))
    for p in added:
        print(f"  + not yet in DBLP ({p['key'].split(':')[0]}): {p['year']} {p['venue']} {p['title']}")

    # The same arXiv paper under two titles (renamed between versions): keep the
    # DBLP record, but take OpenAlex's title, which follows the latest arXiv version.
    def arxiv_id(p):
        m = re.search(r"(\d{4}\.\d{4,5})", p["arxiv"] or (p["url"] if "arxiv" in p["url"].lower() else ""))
        return m.group(1) if m else ""
    seen_arxiv, unique = {}, []
    for p in pubs:
        aid = arxiv_id(p) if p["type"] == "preprint" else ""
        if aid and aid in seen_arxiv:
            kept = seen_arxiv[aid]
            if p["key"].startswith("openalex:") and norm(p["title"]) != norm(kept["title"]):
                print(f"  = same arXiv {aid}: '{kept['title']}' renamed to '{p['title']}'")
                kept["title"] = p["title"]
                kept["topics"] = p["topics"]
            continue
        if aid:
            seen_arxiv[aid] = p
        unique.append(p)
    pubs = unique

    # A preprint later published elsewhere: hide the arXiv copy, keep the link.
    published = {norm(p["title"]): p for p in pubs if p["type"] != "preprint"}
    kept = []
    for p in pubs:
        if p["type"] == "preprint" and norm(p["title"]) in published:
            target = published[norm(p["title"])]
            target["arxiv"] = target["arxiv"] or p["arxiv"] or p["url"]
            continue
        kept.append(p)
    # Newest year first; within a year, alphabetical by venue, then title.
    # Preprints, then entries with no venue, go to the end of their year.
    pubs = sorted(kept, key=lambda p: (-p["year"], p["type"] == "preprint", not p["venue"],
                                       p["venue"].lower(), p["title"].lower()))

    # Hand-assigned topics replace the automatic ones. Keyed by DBLP key or
    # by title, so an entry survives a paper moving from OpenAlex to DBLP.
    fixes = {norm(str(k)): v for k, v in extra_topics.items()}
    for p in pubs:
        fix = extra_topics.get(p["key"]) or fixes.get(norm(p["title"]))
        if fix:
            p["topics"] = list(fix)

    type_labels = venues["type_labels"]
    topic_meta = [{"slug": t["slug"], "label": t["label"]} for t in topics]
    if any("misc" in p["topics"] for p in pubs):
        topic_meta.append({"slug": "misc", "label": "Miscellaneous"})
    research = [p for p in pubs if p["type"] in ("a_conf", "conf", "q1", "journal", "workshop")]
    first = min(p["year"] for p in research)
    stats = {
        "total": len(research),
        "a_conf": sum(p["type"] == "a_conf" for p in pubs),
        "q1": sum(p["type"] == "q1" for p in pubs),
        "first_year": first,
        "years_active": date.today().year - first,
    }
    out = {
        "generated": date.today().isoformat(),
        "stats": stats,
        "types": type_labels,
        "topics": topic_meta,
        "areas": yaml.safe_load(TOPICS.read_text()).get("areas", []),
        "publications": pubs,
    }
    # Keep the old date when nothing changed, so the nightly job commits nothing.
    try:
        prev = json.loads(OUT_JSON.read_text())
        changed = {k: v for k, v in prev.items() if k != "generated"} != \
                  {k: v for k, v in out.items() if k != "generated"}
    except (OSError, ValueError):
        changed = True
    if not changed:
        print("publications unchanged")
        return 0
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    OUT_JS.write_text("window.PUBLICATIONS = " + json.dumps(out, ensure_ascii=False) + ";\n")
    if SITEMAP.exists():
        SITEMAP.write_text(re.sub(r"<lastmod>[^<]*</lastmod>",
                                  f"<lastmod>{date.today().isoformat()}</lastmod>",
                                  SITEMAP.read_text()))

    from collections import Counter
    print(f"{len(raw)} BibTeX entries -> {len(pubs)} publications ({len(dropped)} dropped)")
    for t, c in Counter(p["type"] for p in pubs).most_common():
        print(f"  {type_labels.get(t, t):32s} {c}")
    print("topics:")
    tc = Counter(t for p in pubs for t in p["topics"])
    for t in topic_meta:
        print(f"  {t['label']:40s} {tc[t['slug']]}")
    print("areas:")
    for a in out["areas"]:
        print(f"  {a['label']:40s} {sum(any(t in p['topics'] for t in a['topics']) for p in pubs)}")
    print("stats:", stats)
    return 0


# --------------------------------------------------------------------------
# Cache busting: GitHub Pages lets browsers keep CSS/JS for 10 minutes, so
# index.html references them as file?v=<content hash>; a changed file gets a
# new URL and is fetched at once.
# --------------------------------------------------------------------------

BUSTED = ["assets/css/style.css", "assets/js/site.js", "assets/js/publications-data.js"]


def bump_cache_busters() -> None:
    import hashlib
    index = ROOT / "index.html"
    html = original = index.read_text()
    for asset in BUSTED:
        digest = hashlib.sha256((ROOT / asset).read_bytes()).hexdigest()[:10]
        html = re.sub(re.escape(asset) + r'(\?v=[0-9a-f]*)?"', f'{asset}?v={digest}"', html)
    if html != original:
        index.write_text(html)
        print("index.html: asset versions updated")


if __name__ == "__main__":
    rc = main()
    bump_cache_busters()
    sys.exit(rc)
