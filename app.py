import os
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ----------------------------
# Config
# ----------------------------
EL_NAME = "El"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
USER_AGENT = "SpliceEventBot/1.0 (+https://splice.social)"

SOURCES = [
    {"name": "The Adelphia", "url": "https://www.theadelphia.com/events/"},
    {"name": "Greater Parkersburg", "url": "https://www.greaterparkersburg.com/events/"},
    {"name": "Parkersburg Art Center", "url": "https://www.parkersburgartcenter.org/upcomingcurrent-events"},
]

_cache: Dict[str, Any] = {
    "ts": 0,
    "events": [],
}


# ----------------------------
# Helpers
# ----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fetch_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.text


def safe_json_loads(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None


def flatten_jsonld(obj: Any) -> List[Dict[str, Any]]:
    """
    JSON-LD can be:
      - dict
      - list
      - dict with @graph
    Return list of dict nodes.
    """
    nodes: List[Dict[str, Any]] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if "@graph" in x and isinstance(x["@graph"], list):
                for g in x["@graph"]:
                    walk(g)
            else:
                nodes.append(x)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return [n for n in nodes if isinstance(n, dict)]


def is_event_node(n: Dict[str, Any]) -> bool:
    t = n.get("@type")
    if isinstance(t, list):
        return any(str(x).lower() == "event" for x in t)
    return str(t).lower() == "event"


def parse_datetime_smart(dt_str: str) -> Optional[datetime]:
    """
    Parse dt string; return timezone-aware UTC datetime if possible.
    If dt is naive, assume it's local-ish and convert to UTC by attaching UTC (good enough for filtering past/future).
    If year missing, infer next occurrence.
    """
    if not dt_str:
        return None

    # Some JSON-LD provides ISO with timezone; dateutil handles it.
    try:
        parsed = dtparser.parse(dt_str)
    except Exception:
        return None

    # If no tz info, attach UTC (keeps ordering consistent).
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    # If date string had no year, dateutil will still pick something; we enforce "next occurrence" rule:
    # If parsed is in the past, bump +1 year until it's in the future (max 2 bumps).
    n = now_utc()
    bumped = parsed
    for _ in range(2):
        if bumped >= n:
            break
        bumped = bumped.replace(year=bumped.year + 1)

    return bumped.astimezone(timezone.utc)


def normalize_location(loc: Any) -> str:
    # JSON-LD location may be string or object
    if isinstance(loc, str):
        return loc.strip()
    if isinstance(loc, dict):
        name = loc.get("name") or ""
        addr = loc.get("address") or ""
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress", ""),
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
            ]
            addr_str = ", ".join([p for p in parts if p])
        else:
            addr_str = str(addr) if addr else ""
        return " — ".join([p for p in [name.strip(), addr_str.strip()] if p])
    return ""


def extract_events_from_jsonld(html: str, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    events: List[Dict[str, Any]] = []

    for s in scripts:
        raw = (s.string or "").strip()
        if not raw:
            continue
        data = safe_json_loads(raw)
        if data is None:
            continue

        nodes = flatten_jsonld(data)
        for node in nodes:
            if not is_event_node(node):
                continue

            title = (node.get("name") or "").strip()
            start = node.get("startDate") or node.get("start_date") or ""
            end = node.get("endDate") or ""
            event_url = node.get("url") or source_url

            start_dt = parse_datetime_smart(str(start))
            end_dt = parse_datetime_smart(str(end)) if end else None

            loc = normalize_location(node.get("location"))

            if not title or not start_dt:
                continue

            events.append(
                {
                    "title": title,
                    "start_dt": start_dt.isoformat(),
                    "end_dt": end_dt.isoformat() if end_dt else None,
                    "location": loc,
                    "source": source_name,
                    "url": event_url,
                }
            )

    # If JSON-LD missing, return empty; we can add HTML fallbacks later per-site.
    return events


def refresh_cache_if_needed(force: bool = False) -> None:
    ts = _cache.get("ts", 0) or 0
    if not force and (time.time() - ts) < CACHE_TTL_SECONDS and _cache.get("events"):
        return

    all_events: List[Dict[str, Any]] = []
    for src in SOURCES:
        try:
            html = fetch_html(src["url"])
            extracted = extract_events_from_jsonld(html, src["name"], src["url"])
            all_events.extend(extracted)
        except Exception:
            # Keep going if one source fails
            continue

    # Filter to future-only
    n = now_utc()
    filtered: List[Dict[str, Any]] = []
    for e in all_events:
        try:
            sd = dtparser.isoparse(e["start_dt"])
            if sd.tzinfo is None:
                sd = sd.replace(tzinfo=timezone.utc)
            if sd >= n:
                filtered.append(e)
        except Exception:
            continue

    # Sort by soonest
    filtered.sort(key=lambda x: x["start_dt"])

    _cache["ts"] = time.time()
    _cache["events"] = filtered


def format_events(events: List[Dict[str, Any]], limit: int = 6) -> str:
    if not events:
        return "I’m not seeing any clean upcoming events from my current sources yet. Try **music**, **art**, **classes**, or **this weekend**."

    lines = []
    for e in events[:limit]:
        sd = dtparser.isoparse(e["start_dt"]).astimezone(timezone.utc)
        nice = sd.strftime("%a %b %d, %I:%M %p UTC")
        loc = f" ({e['location']})" if e.get("location") else ""
        lines.append(f"• **{e['title']}** — {nice}{loc}\n  _Source: {e['source']}_")
    return "\n".join(lines)


def classify_query(msg: str) -> str:
    m = msg.lower()
    if any(k in m for k in ["music", "live music", "band", "concert", "show"]):
        return "music"
    if any(k in m for k in ["art", "exhibit", "gallery"]):
        return "art"
    if any(k in m for k in ["class", "classes", "workshop", "camp"]):
        return "classes"
    if any(k in m for k in ["weekend", "this weekend", "friday", "saturday", "sunday"]):
        return "weekend"
    if any(k in m for k in ["today", "tonight"]):
        return "today"
    return "general"


def filter_by_intent(events: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
    if intent == "general":
        return events

    # Very simple keyword filtering for now (we’ll improve this once we confirm each site’s data quality).
    keywords = {
        "music": ["music", "concert", "band", "live", "show"],
        "art": ["art", "exhibit", "gallery"],
        "classes": ["class", "workshop", "camp", "lesson"],
        "weekend": [],  # weekend filtering is date-based; we’ll add later
        "today": [],    # today filtering is date-based; we’ll add later
    }

    ks = keywords.get(intent, [])
    if not ks:
        return events

    out = []
    for e in events:
        t = (e.get("title") or "").lower()
        if any(k in t for k in ks):
            out.append(e)
    return out


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def home():
    return "OK", 200


@app.get("/health")
def health():
    refresh_cache_if_needed()
    return jsonify({"ok": True, "events_cached": len(_cache.get("events", []))}), 200


def handle_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()

    if not msg:
        return jsonify({"message": "Message is required"}), 400

    # Always ensure cache is warm
    refresh_cache_if_needed()

    intent = classify_query(msg)
    events = _cache.get("events", [])
    scoped = filter_by_intent(events, intent)

    # Intro / landing response
    if msg.lower() in ["hi", "hello", "hey"]:
        return jsonify(
            {
                "message": (
                    f"Hi, I’m {EL_NAME} — your insider for everything happening around the MOV.\n\n"
                    "✨ **Today’s Highlights**\n"
                    "• (warming up from live sources)\n\n"
                    "📅 **This Weekend**\n"
                    "• Try: “music this weekend” or “family events”\n\n"
                    "Tell me what kind of vibe you’re looking for: **music, family, art, classes, shows, date night, free stuff**."
                )
            }
        ), 200

    # Main event answer
    reply = format_events(scoped, limit=6)
    return jsonify({"message": reply}), 200


# ✅ Accept BOTH URLs so WP never 404s
@app.post("/chat")
def chat():
    return handle_chat()


@app.post("/el-chat/chat")
def el_chat_chat():
    return handle_chat()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
