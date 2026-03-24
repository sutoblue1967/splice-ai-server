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
import xml.etree.ElementTree as ET

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


def get_event_urls_from_sitemap(sitemap_url: str) -> List[str]:
    urls: List[str] = []

    try:
        r = requests.get(sitemap_url, headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()

        root = ET.fromstring(r.text)

        for url in root.findall(".//{*}loc"):
            link = url.text or ""
            print("SITEMAP URL:", link)

            if "/event" in link:
                urls.append(link)

    except Exception as e:
        print("Sitemap error:", e)

    return urls

def get_adelphia_event_details(event_url: str) -> Dict[str, Any]:
    """
    Visit an Adelphia event page and try to extract:
    - title
    - real event start datetime
    - location
    """
    try:
        html = fetch_html(event_url)
        soup = BeautifulSoup(html, "html.parser")

        # First try JSON-LD, which is usually the cleanest source
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
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
                loc = normalize_location(node.get("location"))

                start_dt = parse_datetime_smart(str(start)) if start else None

                return {
                    "title": title or event_url.split("/")[-2].replace("-", " ").title(),
                    "start_dt": start_dt.isoformat() if start_dt else None,
                    "location": loc or "The Adelphia",
                    "source": "The Adelphia",
                    "url": event_url,
                }

        # Fallback: title from URL, unknown date
        return {
            "title": event_url.split("/")[-2].replace("-", " ").title(),
            "start_dt": None,
            "location": "The Adelphia",
            "source": "The Adelphia",
            "url": event_url,
        }

    except Exception as e:
        print(f"Adelphia page parse failed for {event_url}: {e}")
        return {
            "title": event_url.split("/")[-2].replace("-", " ").title(),
            "start_dt": None,
            "location": "The Adelphia",
            "source": "The Adelphia",
            "url": event_url,
        }


def is_event_node(n: Dict[str, Any]) -> bool:
    t = n.get("@type")
    if isinstance(t, list):
        return any(str(x).lower() == "event" for x in t)
    return str(t).lower() == "event"


def parse_datetime_smart(dt_str: str) -> Optional[datetime]:
    """
    Parse dt string; return timezone-aware UTC datetime if possible.
    If dt is naive, attach UTC to keep comparisons consistent.
    If parsed result is in the past, bump year forward up to 2 times.
    """
    if not dt_str:
        return None

    try:
        parsed = dtparser.parse(dt_str)
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    n = now_utc()
    bumped = parsed
    for _ in range(2):
        if bumped >= n:
            break
        bumped = bumped.replace(year=bumped.year + 1)

    return bumped.astimezone(timezone.utc)


def normalize_location(loc: Any) -> str:
    if isinstance(loc, str):
        return loc.strip()

    if isinstance(loc, dict):
        name = (loc.get("name") or "").strip()
        addr = loc.get("address") or ""

        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress", ""),
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
            ]
            addr_str = ", ".join([p for p in parts if p])
        else:
            addr_str = str(addr).strip() if addr else ""

        return " — ".join([p for p in [name, addr_str] if p])

    return ""


def extract_events_from_html(html: str, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Dict[str, Any]] = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/event/" in href or "/events/" in href:
            title = link.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            full_url = href if href.startswith("http") else source_url.rstrip("/") + "/" + href.lstrip("/")

            events.append({
                "title": title,
                "start_dt": None,  # safer than inventing a fake date
                "location": "",
                "source": source_name,
                "url": full_url,
            })

        if len(events) >= 15:
            break

    return events


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

            if not title:
                continue

            events.append({
                "title": title,
                "start_dt": start_dt.isoformat() if start_dt else None,
                "end_dt": end_dt.isoformat() if end_dt else None,
                "location": loc,
                "source": source_name,
                "url": event_url,
            })

    return events


def refresh_cache_if_needed(force: bool = False) -> None:
    ts = _cache.get("ts", 0) or 0
    if not force and (time.time() - ts) < CACHE_TTL_SECONDS and _cache.get("events"):
        return

    all_events: List[Dict[str, Any]] = []

  # Adelphia sitemap -> visit each event page for real event details
event_urls = get_event_urls_from_sitemap(
    "https://www.theadelphia.com/adelphia_event-sitemap.xml"
)

for url in event_urls[:10]:
    event_data = get_adelphia_event_details(url)
    all_events.append(event_data)

    # Other sources
    for src in SOURCES:
        try:
            html = fetch_html(src["url"])

            extracted = extract_events_from_jsonld(html, src["name"], src["url"])
            if not extracted:
                extracted = extract_events_from_html(html, src["name"], src["url"])

            all_events.extend(extracted)

        except Exception as e:
            print(f"Source failed: {src['name']} -> {e}")
            continue

    # Keep undated events. Only exclude dated events that are clearly in the past.
    n = now_utc()
    filtered: List[Dict[str, Any]] = []

    for e in all_events:
        start_dt = e.get("start_dt")

        if not start_dt:
            filtered.append(e)
            continue

        try:
            sd = dtparser.isoparse(start_dt)
            if sd.tzinfo is None:
                sd = sd.replace(tzinfo=timezone.utc)

            if sd >= n:
                filtered.append(e)
        except Exception:
            filtered.append(e)

    # Dated events first, undated after
    def sort_key(e: Dict[str, Any]):
        start_dt = e.get("start_dt")
        if not start_dt:
            return ("1", "9999-12-31T23:59:59+00:00")
        return ("0", start_dt)

    filtered.sort(key=sort_key)

    _cache["ts"] = time.time()
    _cache["events"] = filtered


def format_events(events: List[Dict[str, Any]], limit: int = 6) -> str:
    if not events:
        return "I’m not seeing any upcoming events from my current sources yet. Try music, art, classes, family, or this weekend."

    lines = []
    for e in events[:limit]:
        title = e.get("title", "Event").strip()
        location = e.get("location", "").strip()
        start_dt = e.get("start_dt")

        if start_dt:
            sd = dtparser.isoparse(start_dt).astimezone()
            nice = sd.strftime("%a, %b %d at %I:%M %p").replace(" 0", " ").replace("at 0", "at ")
        else:
            nice = "Date coming soon"

        if location:
            lines.append(f"{title}\n{nice}\n{location}")
        else:
            lines.append(f"{title}\n{nice}")

    return "\n\n".join(lines)


def classify_query(msg: str) -> str:
    m = msg.lower()

    if any(k in m for k in ["music", "live music", "band", "concert", "show"]):
        return "music"
    if any(k in m for k in ["art", "exhibit", "gallery"]):
        return "art"
    if any(k in m for k in ["class", "classes", "workshop", "camp"]):
        return "classes"
    if any(k in m for k in ["family", "kids", "kid", "children", "child"]):
        return "family"
    if any(k in m for k in ["weekend", "this weekend", "friday", "saturday", "sunday"]):
        return "weekend"
    if any(k in m for k in ["today", "tonight"]):
        return "today"

    return "general"


def filter_by_intent(events: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
    if intent == "general":
        return events

    now = now_utc()

    if intent == "today":
        out = []
        for e in events:
            start_dt = e.get("start_dt")
            if not start_dt:
                continue
            try:
                sd = dtparser.isoparse(start_dt)
                if sd.tzinfo is None:
                    sd = sd.replace(tzinfo=timezone.utc)
                if sd.date() == now.date():
                    out.append(e)
            except Exception:
                continue
        return out

    if intent == "weekend":
        out = []
        for e in events:
            start_dt = e.get("start_dt")
            if not start_dt:
                continue
            try:
                sd = dtparser.isoparse(start_dt)
                if sd.tzinfo is None:
                    sd = sd.replace(tzinfo=timezone.utc)
                if sd.weekday() in [4, 5, 6]:
                    out.append(e)
            except Exception:
                continue
        return out

    keywords = {
        "music": ["music", "concert", "band", "live", "show"],
        "art": ["art", "exhibit", "gallery"],
        "classes": ["class", "workshop", "camp", "lesson"],
        "family": ["family", "kids", "kid", "children", "child"],
    }

    ks = keywords.get(intent, [])
    if not ks:
        return events

    out = []
    for e in events:
        hay = " ".join([
            str(e.get("title", "")),
            str(e.get("location", "")),
            str(e.get("source", "")),
            str(e.get("url", "")),
        ]).lower()

        if any(k in hay for k in ks):
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
    return jsonify({"ok": True, "events_cached": len(_cache.get("events", []))})


@app.get("/events")
def events():
    refresh_cache_if_needed()
    return app.response_class(
        response=json.dumps(_cache.get("events", []), indent=2),
        status=200,
        mimetype="application/json",
    )


def handle_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()

    if not msg:
        return jsonify({"message": "Message is required"}), 400

    refresh_cache_if_needed()

    intent = classify_query(msg)
    events = _cache.get("events", [])
    scoped = filter_by_intent(events, intent)

    if msg.lower() in ["hi", "hello", "hey"]:
        return jsonify({
            "message": (
                f"Hi, I’m {EL_NAME} — your insider for everything happening around the MOV.\n\n"
                "Try asking for music, art, classes, family events, or what’s happening this weekend."
            )
        }), 200

    reply = format_events(scoped, limit=6)
    return jsonify({"message": reply}), 200


@app.post("/chat")
def chat():
    return handle_chat()


@app.post("/el-chat/chat")
def el_chat_chat():
    return handle_chat()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
