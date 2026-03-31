import os
import json
import time
import re
from datetime import datetime, timezone,timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from flask import Flask, request, jsonify
from flask_cors import CORS
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)

EL_NAME = "El"
CACHE_TTL_SECONDS = 6 * 60 * 60
USER_AGENT = "SpliceEventBot/1.0 (+https://splice.social)"

SOURCES = [
    {"name": "Greater Parkersburg", "url": "https://www.greaterparkersburg.com/events/"},
    {"name": "Parkersburg Art Center", "url": "https://www.parkersburgartcenter.org/upcomingcurrent-events"},
]

_cache: Dict[str, Any] = {
    "ts": 0,
    "events": [],
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.google.com/",
    }

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def safe_json_loads(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None


def flatten_jsonld(obj: Any) -> List[Dict[str, Any]]:
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
            if "/event" in link:
                urls.append(link)

    except Exception as e:
        print("Sitemap error:", e)

    return urls


def is_event_node(n: Dict[str, Any]) -> bool:
    t = n.get("@type")
    if isinstance(t, list):
        return any(str(x).lower() == "event" for x in t)
    return str(t).lower() == "event"


def parse_datetime_smart(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None

    try:
        parsed = dtparser.parse(dt_str)
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


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
                "start_dt": None,
                "location": "",
                "source": source_name,
                "url": full_url,
            })

        if len(events) >= 15:
            break

    return events

def extract_greater_parkersburg_events(html: str, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Dict[str, Any]] = []

    headings = soup.find_all(["h2", "h3"])

    for heading in headings:
        title = heading.get_text(" ", strip=True)
        if not title or len(title) < 5:
            continue

        # Look at nearby text after the heading
        block_text = []
        for sib in heading.next_siblings:
            text = ""
            if hasattr(sib, "get_text"):
                text = sib.get_text(" ", strip=True)
            else:
                text = str(sib).strip()

            if text:
                block_text.append(text)

            # Stop once we hit a read-more area or after enough nearby text
            if "Read more" in text or len(block_text) >= 6:
                break

        combined_text = " ".join(block_text)

        # Match lines like: April 2, 2026, 7:00 pm
        match = re.search(
            r"([A-Z][a-z]+ \d{1,2}, \d{4}, \d{1,2}:\d{2} [ap]m)",
            combined_text
        )

def extract_parkersburg_art_center_events(html: str, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Dict[str, Any]] = []

    current_title = None
    current_text = []

    def flush_event():
        nonlocal current_title, current_text, events

        if not current_title:
            return

        title_line = current_title.strip()
        body = " ".join(current_text).strip()

        # Skip clearly non-event items
        lowered = title_line.lower()
        if lowered in ["private painting and pottery parties", "camp creativity registration: now open"]:
            current_title = None
            current_text = []
            return

        # Pull date/time from title first, then body
        combined = title_line + " " + body

        start_dt = None
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?(?:,\s*\d{1,2}(?::\d{2})?\s*[ap]\.?\s*m\.?)?",
            combined,
            re.IGNORECASE
        )

        if match:
            date_text = match.group(0)
            # If no year present, assume current year
            if not re.search(r"\d{4}", date_text):
                date_text = f"{date_text}, {now_utc().year}"
            parsed = parse_datetime_smart(date_text)
            if parsed:
                start_dt = parsed.isoformat()

        # Find a useful URL if one exists near the title
        event_url = source_url
        heading = soup.find(lambda tag: tag.name in ["h2", "h3"] and title_line in tag.get_text(" ", strip=True))
        if heading:
            next_link = heading.find_next("a", href=True)
            if next_link and next_link.get("href"):
                href = next_link["href"]
                event_url = href if href.startswith("http") else source_url.rstrip("/") + "/" + href.lstrip("/")

        events.append({
            "title": re.sub(r":\s*(January|February|March|April|May|June|July|August|September|October|November|December).*", "", title_line, flags=re.IGNORECASE).strip(),
            "start_dt": start_dt,
            "location": "Parkersburg Art Center",
            "source": source_name,
            "url": event_url,
        })

        current_title = None
        current_text = []

    in_past_events = False

    for tag in soup.find_all(["h1", "h2", "h3", "p"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue

        if text.strip().upper() == "PAST EVENTS":
            flush_event()
            in_past_events = True
            break

        if tag.name == "h3":
            flush_event()
            current_title = text
            current_text = []
        elif current_title:
            current_text.append(text)

    if not in_past_events:
        flush_event()

    return events
    
    start_dt = None
        if match:
            parsed = parse_datetime_smart(match.group(1))
            if parsed:
                start_dt = parsed.isoformat()

        # Find the nearest "Read more..." link
        event_url = source_url
        read_more = heading.find_next("a", string=lambda s: s and "Read more" in s)
        if read_more and read_more.get("href"):
            href = read_more["href"]
            event_url = href if href.startswith("http") else source_url.rstrip("/") + "/" + href.lstrip("/")

        events.append({
            "title": title,
            "start_dt": start_dt,
            "location": "Greater Parkersburg Area",
            "source": source_name,
            "url": event_url,
})
        print("🔥 RUNNING GREATER PARKERSBURG PARSER")

       # DEBUG BLOCK (separate, same indent level)
        events.append({
           "title": "DEBUG GREATER PARKERSBURG",
           "start_dt": None,
           "location": "Greater Parkersburg Area",
           "source": source_name,
           "url": source_url,
})


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


def get_adelphia_event_details(event_url: str) -> Dict[str, Any]:
    fallback_title = event_url.split("/")[-2].replace("-", " ").title()

    try:
        html = fetch_html(event_url)
        soup = BeautifulSoup(html, "html.parser")

        title = fallback_title
        h1 = soup.find("h1")
        if h1:
            title_text = h1.get_text(" ", strip=True)
            if title_text:
                title = title_text

        page_text = soup.get_text("\n", strip=True)
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]

        date_text = None
        show_text = None

        for i, line in enumerate(lines):
            if line.lower() == "date" and i + 1 < len(lines):
                date_text = lines[i + 1]
            if line.lower() == "showtime" and i + 1 < len(lines):
                show_text = lines[i + 1]

        start_dt = None

        if date_text and show_text:
            match = re.search(r"(\d{1,2}:\d{2}\s*[ap]m)", show_text, re.IGNORECASE)
            if not match and "show starts at" in show_text.lower():
                match = re.search(r"show starts at\s*(\d{1,2}:\d{2}\s*[ap]m)", show_text, re.IGNORECASE)

            if match:
                combined = f"{date_text} {match.group(1)}"
                parsed = parse_datetime_smart(combined)
                if parsed:
                    start_dt = parsed.isoformat()

        return {
            "title": title,
            "start_dt": start_dt,
            "location": "The Adelphia",
            "source": "The Adelphia",
            "url": event_url,
        }

    except Exception as e:
        print(f"Adelphia detail parse failed: {event_url} -> {e}")
        return {
            "title": fallback_title,
            "start_dt": None,
            "location": "The Adelphia",
            "source": "The Adelphia",
            "url": event_url,
        }


def refresh_cache_if_needed(force: bool = False) -> None:
    ts = _cache.get("ts", 0) or 0
    if not force and (time.time() - ts) < CACHE_TTL_SECONDS and _cache.get("events"):
        return

    all_events: List[Dict[str, Any]] = []

    event_urls = get_event_urls_from_sitemap(
        "https://www.theadelphia.com/adelphia_event-sitemap.xml"
    )

    for url in event_urls[:10]:
        event_data = get_adelphia_event_details(url)
        all_events.append(event_data)

    for src in SOURCES:
        try:
            html = fetch_html(src["url"])

            if src["name"] == "Greater Parkersburg":
                extracted = extract_greater_parkersburg_events(html, src["name"], src["url"])
            elif src["name"] == "Parkersburg Art Center":
                extracted = extract_parkersburg_art_center_events(html, src["name"], src["url"])
            else:
                extracted = extract_events_from_jsonld(html, src["name"], src["url"])
                if not extracted:
                    extracted = extract_events_from_html(html, src["name"], src["url"])

            all_events.extend(extracted)

        except Exception as e:
            print(f"Source failed: {src['name']} -> {e}")
            continue

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
        return "I’m not seeing any upcoming events from my current sources yet. Try music, art, classes, family, or a general event question."

    lines = []
    for e in events[:limit]:
        title = e.get("title", "Event").strip()
        location = e.get("location", "").strip()
        start_dt = e.get("start_dt")

        if start_dt:
            try:
                sd = dtparser.isoparse(start_dt).astimezone()
                nice = sd.strftime("%a, %b %d at %I:%M %p").replace(" 0", " ").replace("at 0", "at ")
            except Exception:
                nice = "Date coming soon"
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
                sd = sd.astimezone()
                if sd.date() == now.astimezone().date():
                    out.append(e)
            except Exception:
                continue
        return out

    if intent == "weekend":
        out = []
        local_now = now.astimezone()

        # Find this coming Friday/Saturday/Sunday window
        days_until_friday = (4 - local_now.weekday()) % 7
        friday = (local_now + timedelta(days=days_until_friday)).date()
        sunday = friday + timedelta(days=2)

        for e in events:
            start_dt = e.get("start_dt")
            if not start_dt:
                continue
            try:
                sd = dtparser.isoparse(start_dt)
                if sd.tzinfo is None:
                    sd = sd.replace(tzinfo=timezone.utc)
                sd = sd.astimezone()

                if friday <= sd.date() <= sunday:
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


@app.get("/")
def home():
    return "OK", 200


@app.get("/health")
def health():
    refresh_cache_if_needed(force=True)
    return jsonify({
        "ok": True,
        "events_cached": len(_cache.get("events", [])),
        "build": "clean-reset-v2",
    })


@app.get("/events")
def events():
    refresh_cache_if_needed(force=True)
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

    refresh_cache_if_needed(force=True)

    intent = classify_query(msg)
    events = _cache.get("events", [])
    scoped = filter_by_intent(events, intent)

    if msg.lower() in ["hi", "hello", "hey"]:
        return jsonify({
            "message": (
                f"Hi, I’m {EL_NAME} — your insider for everything happening around the MOV.\n\n"
                "Try asking for music, art, classes, family events, or a general event question."
            )
        }), 200

    reply_body = format_events(scoped, limit=6)

    if intent == "weekend":
        intro = "Here are some great events I found for this weekend:"
        outro = "\n\nWant me to narrow that down to music, family-friendly, or something more laid-back?"
    elif intent == "music":
        intro = "Here are some music events I found:"
        outro = "\n\nWant more like this, or want me to look for something family-friendly or artsy?"
    elif intent == "art":
        intro = "Here are some art-related events I found:"
        outro = "\n\nWant me to keep going with art, or switch to music, family, or weekend events?"
    elif intent == "family":
        intro = "Here are some family-friendly events I found:"
        outro = "\n\nWant more family options, or want me to look for music or weekend events too?"
    elif intent == "classes":
        intro = "Here are some classes and workshops I found:"
        outro = "\n\nWant me to keep looking for classes, or switch to music, family, or weekend events?"
    else:
        intro = "Here are some great events I found:"
        outro = "\n\nWant me to narrow it down by music, family-friendly, art, or this weekend?"

    reply = intro + "\n\n" + reply_body + outro
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
