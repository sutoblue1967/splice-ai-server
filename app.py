import os
import re
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

EL_NAME = "El"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours

HEADERS = {
    "User-Agent": "SpliceElBot/1.0 (+https://splice.social)"
}

SOURCES = [
    {
        "name": "The Adelphia",
        "category": "music",
        "urls": ["https://www.theadelphia.com/events/"],
    },
    {
        "name": "Greater Parkersburg",
        "category": "community",
        "urls": ["https://www.greaterparkersburg.com/events/"],
    },
    {
        "name": "Parkersburg Art Center",
        "category": "arts",
        "urls": [
            "http://parkersburgartcenter.org/exhibits",
            "https://www.parkersburgartcenter.org/upcomingcurrent-events",
            "https://www.parkersburgartcenter.org/adult-and-teen-classes",
            "https://www.parkersburgartcenter.org/children-and-family-classes",
            "https://www.parkersburgartcenter.org/camp-creativity",
        ],
    },
]

# In-memory cache (good enough for v1 MVP)
CACHE = {
    "ts": 0,
    "events": [],
    "errors": []
}


# ----------------------------
# Utilities
# ----------------------------
MONTH_RE = re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b", re.I)
DATEISH_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b")

def now_local() -> datetime:
    # server time is fine for MVP; if you want strict ET later we’ll add pytz/zoneinfo
    return datetime.now()

def safe_parse_date(text: str) -> Optional[datetime]:
    t = (text or "").strip()
    if not t:
        return None
    # Heuristic: only try parsing if it looks date-like
    if not (MONTH_RE.search(t) or DATEISH_RE.search(t) or re.search(r"\b\d{4}\b", t)):
        return None
    try:
        return dtparser.parse(t, fuzzy=True, default=now_local())
    except Exception:
        return None

def weekend_range(base: datetime) -> (datetime, datetime):
    # Next Sat/Sun relative to today
    # weekday: Mon=0 ... Sun=6
    days_until_sat = (5 - base.weekday()) % 7
    sat = (base + timedelta(days=days_until_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
    sun = (sat + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    return sat, sun

def event_key(e: Dict) -> str:
    return f"{e.get('source','')}|{e.get('title','')}|{e.get('start','')}|{e.get('url','')}"

def normalize_event(title: str, start: Optional[datetime], url: str, source: str, category: str, raw_date_text: str = "") -> Dict:
    return {
        "title": (title or "").strip(),
        "start": start.isoformat() if start else None,
        "date_text": raw_date_text.strip(),
        "url": url,
        "source": source,
        "category": category,
    }


# ----------------------------
# Scraping helpers
# ----------------------------
def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text

def parse_jsonld_events(html: str, source: str, category: str) -> List[Dict]:
    """Many event sites include schema.org JSON-LD with @type: Event."""
    out = []
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for s in scripts:
        txt = (s.string or "").strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue

        # JSON-LD can be object, list, or graph
        nodes = []
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                nodes = data["@graph"]
            else:
                nodes = [data]

        for node in nodes:
            if not isinstance(node, dict):
                continue
            t = node.get("@type") or node.get("type")
            if isinstance(t, list):
                is_event = any(str(x).lower() == "event" for x in t)
            else:
                is_event = str(t).lower() == "event"
            if not is_event:
                continue

            title = node.get("name") or ""
            start_raw = node.get("startDate") or ""
            url = node.get("url") or ""
            start_dt = None
            try:
                if start_raw:
                    start_dt = dtparser.parse(start_raw)
            except Exception:
                start_dt = None

            if title and url:
                out.append(normalize_event(title, start_dt, url, source, category, raw_date_text=start_raw))
    return out

def parse_basic_event_links(html: str, base_url: str, source: str, category: str) -> List[Dict]:
    """
    Fallback parser:
    - pulls links that have date-ish text nearby
    - works surprisingly well for MVP, but source-specific parsers can be added later.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []

    # Candidate blocks: list items, cards, article blocks
    candidates = soup.find_all(["article", "li", "div", "section"], limit=2000)

    for block in candidates:
        a = block.find("a", href=True)
        if not a:
            continue

        title = a.get_text(" ", strip=True)
        href = a["href"].strip()
        if not title or len(title) < 4:
            continue

        # make absolute url
        if href.startswith("/"):
            url = base_url.rstrip("/") + href
        elif href.startswith("http"):
            url = href
        else:
            url = base_url.rstrip("/") + "/" + href.lstrip("/")

        text = block.get_text(" ", strip=True)
        # find a short date-ish snippet
        start_dt = safe_parse_date(text)
        if not start_dt:
            continue

        out.append(normalize_event(title, start_dt, url, source, category, raw_date_text=text))

    # de-dupe
    uniq = {}
    for e in out:
        uniq[event_key(e)] = e
    return list(uniq.values())


def scrape_source(source_cfg: Dict) -> (List[Dict], List[str]):
    events = []
    errors = []
    for url in source_cfg["urls"]:
        try:
            html = fetch_html(url)

            # Try JSON-LD first (best)
            got = parse_jsonld_events(html, source_cfg["name"], source_cfg["category"])

            # Fallback
            if not got:
                base = re.match(r"^(https?://[^/]+)", url)
                base_url = base.group(1) if base else url
                got = parse_basic_event_links(html, base_url, source_cfg["name"], source_cfg["category"])

            events.extend(got)
        except Exception as e:
            errors.append(f"{source_cfg['name']} ({url}): {str(e)}")

    # de-dupe across urls
    uniq = {}
    for e in events:
        uniq[event_key(e)] = e
    return list(uniq.values()), errors


# ----------------------------
# Cache + selection logic
# ----------------------------
def refresh_cache_if_needed(force: bool = False):
    now_ts = time.time()
    if not force and (now_ts - CACHE["ts"] < CACHE_TTL_SECONDS) and CACHE["events"]:
        return

    all_events = []
    all_errors = []

    for src in SOURCES:
        evs, errs = scrape_source(src)
        all_events.extend(evs)
        all_errors.extend(errs)

    # keep only upcoming-ish events (past ones get noisy)
    now_dt = now_local()
    upcoming = []
    for e in all_events:
        if not e.get("start"):
            continue
        try:
            dt = dtparser.parse(e["start"])
        except Exception:
            continue
        if dt >= (now_dt - timedelta(hours=6)):
            upcoming.append(e)

    # sort by start time
    upcoming.sort(key=lambda x: x.get("start") or "")

    CACHE["ts"] = now_ts
    CACHE["events"] = upcoming
    CACHE["errors"] = all_errors


def select_today(events: List[Dict], base: datetime) -> List[Dict]:
    start = base.replace(hour=0, minute=0, second=0, microsecond=0)
    end = base.replace(hour=23, minute=59, second=59, microsecond=0)
    out = []
    for e in events:
        try:
            dt = dtparser.parse(e["start"])
        except Exception:
            continue
        if start <= dt <= end:
            out.append(e)
    return out[:6]

def select_weekend(events: List[Dict], base: datetime) -> List[Dict]:
    sat, sun = weekend_range(base)
    out = []
    for e in events:
        try:
            dt = dtparser.parse(e["start"])
        except Exception:
            continue
        if sat <= dt <= sun:
            out.append(e)
    return out[:8]

def format_event_line(e: Dict) -> str:
    try:
        dt = dtparser.parse(e["start"]) if e.get("start") else None
        when = dt.strftime("%a %b %-d, %-I:%M %p") if dt else "TBD"
    except Exception:
        when = "TBD"
    return f"• {e.get('title','').strip()} — {when} ({e.get('source')})"


def welcome_message(events: List[Dict]) -> str:
    base = now_local()
    today = select_today(events, base)
    weekend = select_weekend(events, base)

    lines = []
    lines.append(f"Hi, I’m {EL_NAME} — your insider for everything happening around the MOV.\n")

    lines.append("✨ **Today’s Highlights**")
    if today:
        lines.extend([format_event_line(e) for e in today])
    else:
        lines.append("• No solid “today” hits found yet — ask me for *this weekend* or *live music* and I’ll pull what’s coming up.")

    lines.append("\n📅 **This Weekend**")
    if weekend:
        lines.extend([format_event_line(e) for e in weekend])
    else:
        lines.append("• Weekend list is still warming up — try: “music this weekend” or “family events this weekend”")

    lines.append("\nTell me what kind of vibe you’re looking for: **music, family, art, classes, shows, date night, free stuff**…")
    return "\n".join(lines)


def answer_query(user_text: str, events: List[Dict]) -> str:
    t = (user_text or "").lower()
    base = now_local()

    # quick intent filters
    if "today" in t:
        picks = select_today(events, base)
        if not picks:
            return "I’m not seeing strong “today” items yet from the sources — want *this weekend* or *music*?"
        return "✨ **Today**\n" + "\n".join(format_event_line(e) for e in picks)

    if "weekend" in t:
        picks = select_weekend(events, base)
        if not picks:
            return "Weekend is quiet in the feed right now — want me to search *music* or *art classes* instead?"
        return "📅 **This Weekend**\n" + "\n".join(format_event_line(e) for e in picks)

    # category hints
    if any(k in t for k in ["art", "exhibit", "gallery", "class", "camp"]):
        picks = [e for e in events if e.get("source") == "Parkersburg Art Center"]
        return "🎨 **Parkersburg Art Center**\n" + "\n".join(format_event_line(e) for e in picks[:10]) if picks else "I’m not pulling Art Center items yet — I’ll keep refreshing the feed."

    if any(k in t for k in ["music", "band", "concert", "live"]):
        picks = [e for e in events if e.get("source") in ["The Adelphia"]]
        return "🎸 **Live Music / Adelphia**\n" + "\n".join(format_event_line(e) for e in picks[:10]) if picks else "I’m not seeing music items yet — I’ll keep refreshing."

    # default
    return "Tell me: **today**, **this weekend**, **music**, **art**, **classes**, **family**, or **date night** — and I’ll pull the best matches."


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def home():
    return "OK", 200

@app.get("/health")
def health():
    refresh_cache_if_needed(force=False)
    return jsonify({
        "ok": True,
        "cached": bool(CACHE["events"]),
        "cache_age_seconds": int(time.time() - CACHE["ts"]) if CACHE["ts"] else None,
        "event_count": len(CACHE["events"]),
        "errors_count": len(CACHE["errors"]),
    }), 200

@app.get("/events")
def events():
    refresh_cache_if_needed(force=False)
    return jsonify({
        "events": CACHE["events"],
        "errors": CACHE["errors"],
        "cache_age_seconds": int(time.time() - CACHE["ts"]) if CACHE["ts"] else None,
    }), 200

def handle_chat():
    refresh_cache_if_needed(force=False)

    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()

    if not msg:
        return jsonify({"message": "Message is required"}), 400

    if msg == "__WELCOME__":
        return jsonify({"message": welcome_message(CACHE["events"])}), 200

    return jsonify({"message": answer_query(msg, CACHE["events"])}), 200

@app.post("/chat")
def chat():
    return handle_chat()

@app.post("/el-chat/chat")
def el_chat_chat():
    return handle_chat()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
