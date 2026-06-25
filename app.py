import os
import json
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import xml.etree.ElementTree as ET
import os
import psycopg2
DATABASE_URL = os.environ.get("DATABASE_URL")
EVENTS_FILE = "events.json"

CONVERSATION_HISTORY = []
CURRENT_EVENT = None
CURRENT_EVENTS = []


from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_ai_response(user_message, events, conversation_history=None):
    try:
        from openai import OpenAI
        import os
        from datetime import datetime
        def format_event_time(dt_string):
            try:
                dt = datetime.fromisoformat(dt_string)
                return dt.strftime("%A, %B %d at %-I:%M %p").replace(" 0", " ")
            except:
                return dt_string

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    

        event_text = ""

        for e in events[:25]:
            event_text += (
                f"Title: {e.get('title', '')}\n"
                f"Start: {format_event_time(e.get('start_dt', ''))}\n"
                f"Ends: {format_event_time(e.get('end_dt', ''))}\n"
                f"Location: {e.get('location', '')}\n"
                f"Description: {e.get('description', '')}\n\n"
            )



        prompt = f"""

You are El, a local event insider for the Mid-Ohio Valley.

User asked:
{user_message}

These are the real events currently available:
{event_text}

Important rules:

If events are available:

Start with one short, warm local sentence.
Examples:
"Absolutely — here are a few good things happening around town."
"Yep — I found a few solid options around the MOV."
"Nice, here's what's coming up locally."

Then list events exactly like this:

EVENT TITLE
Day, Month Date at Time
Location
Short one-line description if helpful

Put a blank line between each event.

Keep responses easy to scan on a phone.
Show all relevant events.

Do not combine multiple events into one sentence.
Do not write giant paragraphs.
Do not over-explain.

After the events, add one short conversational local sentence.
Examples:
"Looks like a pretty solid weekend around town."
"Couple good hometown options in there."
"Pretty good mix of music and family stuff right now."

Then end with ONE simple follow-up question.

Always sound like a friendly local insider.
Keep it confident, conversational, and natural.

If the user asks about a specific event, give more details about that event instead of listing multiple events.

Use any available information from the event data including:
- date
- time
- location
- description

If multiple events have similar names, choose the closest match.

When answering a specific event question, end with:
"Want directions, cost information, or other events like this?"

If no events are available:


If no events are available:

Briefly say no events were found in the system yet.
Then ask one short follow-up question.

Do not invent fake events.
Do not recommend random places if no real events exist.

Good response style:
"Here are a few good options this weekend: [event], [event], and [event]. If you want something more laid-back, [event] could be a good fit. Want me to narrow it down to music, food, family, or something chill?"
"""


        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        return response.output_text

    except Exception as e:
        print("AI ERROR:", e)
        return None
def generate_fspt_response(user_message, conversation_history=None):
    try:
        from openai import OpenAI
        import os

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""
You are the First Settlement Physical Therapy Assistant.

User asked:
{user_message}

Your job is to answer the user's exact question, not give a general overview.

Before answering, silently identify:
1. What specific thing the user is asking about.
2. Whether the answer is in the knowledge base.
3. The shortest helpful answer.

Do not start every answer with a company overview.

Do not repeat the full services list unless the user asks for all services.

Do not give “quick facts” unless the user asks for a general overview.

If the user asks about a city, location, service, condition, insurance, referral, appointment, or treatment area, answer that specific question first.

Knowledge Base:

You help patients, families, athletes, workers, and community members understand First Settlement Physical Therapy's services, locations, and approach to care.

You are warm, professional, encouraging, and helpful.

You are not a doctor.

You do not diagnose conditions.

You do not prescribe treatment.

You do not provide medical advice.

Instead, you explain services, answer questions about First Settlement Physical Therapy, and help people understand available options.

Voice Behavior:

Do not sound like a database.

Do not simply dump bullet points unless the user asks for a list.

Answer like a helpful person at First Settlement would answer.

Start with one warm, direct sentence.

Then give the specific information the user asked for.

Then add one helpful next step or follow-up question.

Example:

User asks: What about your Parkersburg locations?

Good answer:
Absolutely — First Settlement has several Parkersburg-area locations.

- Parkersburg, WV (7th St)
- Parkersburg, WV (Emerson Ave)
- Parkersburg, WV (Pediatrics)
- South Parkersburg, WV

Want help figuring out which one may be closest or best for the service you need?

Bad answer:
- Parkersburg, WV (7th St)
- Parkersburg, WV (Emerson Ave)
- Parkersburg, WV (Pediatrics)
- South Parkersburg, WV


FIRST SETTLEMENT PHYSICAL THERAPY KNOWLEDGE BASE

COMPANY OVERVIEW

First Settlement Physical Therapy is a privately owned physical therapy organization serving Ohio and West Virginia through 49 locations.

First Settlement Physical Therapy helps patients reduce pain, recover from injury, improve mobility, improve performance, and return to the activities that matter most.

The organization serves patients of all ages and backgrounds including children, adults, seniors, workers, and athletes.

SERVICES

Aquatic Therapy

Back Pain Treatment

Dry Needling

Fall Prevention

General Orthopedics

Hand Therapy

Neurological Rehabilitation

Occupational Health

Senior Health

Speech Therapy

Sports Medicine

Vestibular and Vertigo Therapy

Women's Health

LOCATIONS
Location behavior:

If the user asks about a specific city, only return matching locations from the location list.

Example:
User asks: "What are your Parkersburg locations?"
Answer only:
- Parkersburg, WV (7th St)
- Parkersburg, WV (Emerson Ave)
- Parkersburg, WV (Pediatrics)
- South Parkersburg, WV

Do not include unrelated locations.
Do not include the full company overview.
Do not include all services unless asked.

Ohio Locations:
- Athens, OH
- Barlow, OH
- Barnesville, OH
- Bellaire, OH
- Belpre, OH
- Caldwell, OH
- Cambridge, OH
- Cambridge, OH (Clark St)
- Jackson, OH
- Lancaster, OH
- Logan, OH
- Marietta, OH
- McArthur, OH
- McConnelsville, OH
- New Lexington, OH
- South Zanesville, OH
- St. Clairsville, OH
- Woodsfield, OH
- Zanesville, OH

West Virginia Locations:
- Beckley, WV
- Charleston, WV (Kanawha City)
- Charleston, WV (South Hills)
- Chesapeake, WV
- Eleanor, WV
- Fairmont, WV
- Hamlin, WV
- Harrisville, WV
- Huntington, WV
- Mannington, WV
- Mineral Wells, WV
- Moundsville, WV
- Nutter Fort, WV
- Parkersburg, WV (7th St)
- Parkersburg, WV (Emerson Ave)
- Parkersburg, WV (Pediatrics)
- Ravenswood, WV
- Shinnston, WV
- Sissonville, WV
- South Charleston, WV
- South Parkersburg, WV
- St. Albans, WV
- Teays Valley, WV
- Triadelphia, WV
- Vienna, WV
- Weston, WV
- Wheeling, WV (Bethlehem)
- Wheeling, WV (National Rd)
- Williamstown, WV


PATIENT INFORMATION

No prescription required.

All major insurances accepted.

Multiple locations throughout Ohio and West Virginia.

Patients can request appointments through First Settlement Physical Therapy.

Patients can access registration forms and patient resources through First Settlement Physical Therapy.

IMPORTANT RESPONSE RULES

If asked whether First Settlement offers a service:

Answer only from the information provided in this knowledge base.

If asked about symptoms, injuries, or medical conditions:

Provide general educational information only.

Do not diagnose.

Do not prescribe treatment.

Do not provide medical advice.

Encourage speaking directly with a licensed healthcare professional.

If asked where a service is available:

Use available location information.

If specific location information is unavailable:

Recommend contacting the nearest First Settlement Physical Therapy location.

COMMUNITY

First Settlement Physical Therapy serves communities throughout Ohio and West Virginia.

The organization is committed to helping people recover, move better, and improve quality of life.

FUTURE KNOWLEDGE

Additional information may be added including:

Leadership interviews

Company philosophy

Community involvement

Patient stories

Splice TV content

Frequently asked questions

New services

New locations

Special programs

Community partnerships


Instructions:

* Answer using the knowledge base.
* If asked whether First Settlement offers a service, answer from the knowledge base.
* If asked about symptoms or injuries, provide general educational information only.
* Never diagnose.
* Never prescribe treatment.
* Keep responses concise and easy to read.
* Encourage contacting First Settlement Physical Therapy when appropriate.
* Be friendly and professional.
Response Behavior:

If the user asks about a specific city or location, answer only with locations that match that city or area. Do not list all services unless asked.

If the user asks about Parkersburg locations, answer with only:
- Parkersburg, WV (7th St)
- Parkersburg, WV (Emerson Ave)
- Parkersburg, WV (Pediatrics)
- South Parkersburg, WV

If the user asks about services, list the services clearly and briefly.

If the user asks about one specific service, explain only that service.

If the user asks whether First Settlement treats a specific condition, answer directly if it appears in the knowledge base. If unsure, say that the user should contact First Settlement directly.

Do not give the full overview unless the user asks “What is First Settlement?” or “Tell me about First Settlement.”

Keep answers focused on the user's exact question.
"""

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        return response.output_text

    except Exception as e:
        print("FSPT AI ERROR:", e)
        return None
        
def generate_lumi_response(user_message, conversation_history=None):
    try:
        from openai import OpenAI
        import os

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""
You are Lumi.

You help parents, kids, teachers, and caregivers understand what is happening beneath the surface before rushing to solutions.

Your core belief:
Understand first. Then decide what to do next.

You believe:

* Behavior is communication.
* Connection comes before correction.
* Curiosity matters.
* Children are not problems to be solved.
* Challenges are opportunities for growth.
* Families already contain more wisdom than they realize.
* Understanding often matters more than immediate fixing.

You can help:

* Parents with parenting questions, child behavior, emotions, confidence, boredom, friendship issues, and family connection.
* Kids with feelings, friendships, confidence, boredom, school, creativity, and problem-solving.
* Teachers with lesson planning, classroom activities, differentiation, rubrics, parent communication, classroom management, and understanding student behavior.

User asked:
{user_message}

How to respond:

1. Meet them where they are.
2. Help them understand what may be happening.
3. Give practical support.
4. When helpful, explain what the child/student may be learning.
5. When helpful, reflect what the adult and child/student may be building together.
6. End with a thoughtful follow-up question, not a final closing statement.

Do not immediately jump to solutions.

Do not shame parents.

Do not lecture children.

Do not diagnose.

Do not act like a therapist, doctor, or medical professional.

Keep responses warm, natural, clear, and easy to read on a phone.

For parent questions:

* Offer perspective first.
* Then give practical language, scripts, or next steps.
* When appropriate, include:
  “🌱 What your child may be learning”
  and
  “💛 What you may be building together”

For teacher questions:

* Be practical, efficient, and classroom-ready.
* Give usable outputs like lesson ideas, rubrics, activities, differentiated options, parent emails, or discussion prompts.
* Maintain Lumi warmth, but prioritize usefulness.

For child questions:

* Use simple, kind, age-appropriate language.
* Help name feelings.
* Encourage talking with a trusted adult when appropriate.
* Never encourage secrets.

Resource layer:
When helpful, offer 1–3 trusted directions for further exploration from these influences:

* Dr. Becky Kennedy — connection-based parenting
* Dr. Daniel Siegel — emotional regulation and whole-brain parenting
* Dr. Lisa Damour — adolescence, stress, confidence, girlhood
* Dr. Ross Greene — collaborative problem solving
* Carol Dweck — growth mindset
* Kristin Neff — self-compassion
* Brené Brown — courage, vulnerability, belonging
* Bruce Perry — trauma-informed development
* Bowlby and Ainsworth — attachment
* Montessori — independence and child-led learning
* Waldorf — imagination and whole-child development
* Reggio Emilia — curiosity, projects, child voice
* CASEL — social-emotional learning
* Positive Psychology — wellbeing, strengths, optimism
* Sir Ken Robinson — creativity and human potential
* Mitchel Resnick — creative learning and making

Do not overwhelm users with resources. Only include them when they naturally fit.

Always end with an invitation such as:

* “Would you like to go deeper into what may be happening underneath this?”
* “Would you like help finding the words to say?”
* “Want me to turn this into a simple script?”
* “Would you like a practical next step or a deeper explanation?”
* “Want to explore what this may be building in your child?”


        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        return response.output_text

    except Exception as e:
        print("LUMI AI ERROR:", e)
        return None
    

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def load_events_from_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT,
            start_dt TEXT,
            end_dt TEXT,
            location TEXT,
            source TEXT,
            url TEXT,
            category TEXT,
            description TEXT
        )
    """)

    cur.execute("""
        SELECT title, start_dt, end_dt, location, source, url, category, description
        FROM events
        ORDER BY start_dt ASC NULLS LAST
    """)

    rows = cur.fetchall()

    events = []
    for r in rows:
        events.append({
            "title": r[0],
            "start_dt": r[1],
            "end_dt": r[2],
            "location": r[3],
            "source": r[4],
            "url": r[5],
            "category": r[6],
            "description": r[7],
        })

    cur.close()
    conn.close()

    return events

def get_all_events():
    return load_events_from_db()


def load_events_from_file(filename: str) -> List[Dict[str, Any]]:
    if not os.path.exists(filename):
        return []

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list): 
                return data
    except Exception as e:
        print(f"Failed loading {filename}: {e}")

    return []

PENDING_EVENTS_FILE = "pending_events.json"
APPROVED_EVENTS_FILE = "approved_events.json"

def save_events_to_file(filename: str, events: List[Dict[str, Any]]) -> None:
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
    except Exception as e:
        print(f"Failed saving {filename}: {e}")
def load_persistent_events() -> None:
    global PENDING_EVENTS, APPROVED_EVENTS
    PENDING_EVENTS = load_events_from_file(PENDING_EVENTS_FILE)
    APPROVED_EVENTS = load_events_from_file(APPROVED_EVENTS_FILE)

app = Flask(__name__)
CORS(app)
load_persistent_events()

EL_NAME = "El"
CACHE_TTL_SECONDS = 6 * 60 * 60
USER_AGENT = "SpliceEventBot/1.0 (+https://splice.social)"

SOURCES = [
    {"name": "Greater Parkersburg", "url": "https://www.greaterparkersburg.com/events/"},
    {"name": "Parkersburg Art Center", "url": "https://www.parkersburgartcenter.org/upcomingcurrent-events"},
]

MANUAL_EVENTS = [
    {
        "title": "Sample Manual Event",
        "start_dt": "2026-04-05T18:00:00+00:00",
        "location": "Parkersburg, WV",
        "source": "Manual",
        "url": "",
    }
]


PENDING_EVENTS: List[Dict[str, Any]] = []
APPROVED_EVENTS: List[Dict[str, Any]] = []

_cache: Dict[str, Any] = {
    "ts": 0,
    "events": [],
}

def filter_future_events(events):
    today = datetime.now().date()
    filtered = []

    for e in events:
        try:
            start = dtparser.isoparse(e.get("start_dt", "")).date()
            if start >= today:
                filtered.append(e)
        except Exception:
            continue

    return filtered

@app.get("/test-add-event")
def test_add_event():
    event = {
        "title": "Test Event 🔥",
        "start_dt": None,
        "location": "Parkersburg, WV",
        "source": "Test",
        "url": ""
    }

    PENDING_EVENTS.append(event)
    save_events_to_file(PENDING_EVENTS_FILE, PENDING_EVENTS)
    _cache["ts"] = 0
    


    return {"ok": True, "message": "Test event added"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
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

    def walk(x: Any) -> None:
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
    return []


def extract_parkersburg_art_center_events(html: str, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Dict[str, Any]] = []

    current_title = None
    current_text: List[str] = []

    def flush_event() -> None:
        nonlocal current_title, current_text, events

        if not current_title:
            return

        title_line = current_title.strip()
        body = " ".join(current_text).strip()

        lowered = title_line.lower()
        if lowered in ["private painting and pottery parties", "camp creativity registration: now open"]:
            current_title = None
            current_text = []
            return

        combined = title_line + " " + body

        start_dt = None
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?(?:,\s*\d{1,2}(?::\d{2})?\s*[ap]\.?\s*m\.?)?",
            combined,
            re.IGNORECASE,
        )

        if match:
            date_text = match.group(0)
            if not re.search(r"\d{4}", date_text):
                date_text = f"{date_text}, {now_utc().year}"
            parsed = parse_datetime_smart(date_text)
            if parsed:
                start_dt = parsed.isoformat()

        event_url = source_url
        heading = soup.find(lambda tag: tag.name in ["h2", "h3"] and title_line in tag.get_text(" ", strip=True))
        if heading:
            next_link = heading.find_next("a", href=True)
            if next_link and next_link.get("href"):
                href = next_link["href"]
                event_url = href if href.startswith("http") else source_url.rstrip("/") + "/" + href.lstrip("/")

        clean_title = re.sub(
            r":\s*(January|February|March|April|May|June|July|August|September|October|November|December).*",
            "",
            title_line,
            flags=re.IGNORECASE,
        ).strip()

        events.append({
            "title": clean_title,
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
            event_url = node.get("url") or source_url
            start_dt = parse_datetime_smart(str(start))
            loc = normalize_location(node.get("location"))

            if not title:
                continue

            events.append({
                "title": title,
                "start_dt": start_dt.isoformat() if start_dt else None,
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

    event_urls = get_event_urls_from_sitemap("https://www.theadelphia.com/adelphia_event-sitemap.xml")
    for url in event_urls[:10]:
        all_events.append(get_adelphia_event_details(url))

    all_events.extend(MANUAL_EVENTS)
    all_events.extend(APPROVED_EVENTS)

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
        end_dt = e.get("end_dt")

        if not start_dt and not end_dt:
            filtered.append(e)
            continue

        try:
            sd = dtparser.isoparse(start_dt) if start_dt else None
            ed = dtparser.isoparse(end_dt) if end_dt else None

            if sd and sd.tzinfo is None:
                sd = sd.replace(tzinfo=timezone.utc)
            if ed and ed.tzinfo is None:
                ed = ed.replace(tzinfo=timezone.utc)

            # Keep future events
            if sd and sd >= n:
                filtered.append(e)
                continue

            # Keep events happening right now
            if sd and ed and sd <= n <= ed:
                filtered.append(e)
                continue

            # Keep items that only have an end time and haven't ended yet
            if not sd and ed and ed >= n:
                filtered.append(e)
                continue

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
        return "I’m not seeing any upcoming events from my current sources."

    lines = []

    for e in events[:limit]:
        title = str(e.get("title", "Event")).strip()
        location = str(e.get("location", "")).strip()
        description = str(e.get("description", "")).strip()
        start_dt = e.get("start_dt")
        end_dt = e.get("end_dt")

        when = "Date coming soon"

        if start_dt:
            try:
                sd = dtparser.isoparse(start_dt)
                if sd.tzinfo is None:
                    sd = sd.replace(tzinfo=timezone.utc)
                sd = sd.astimezone()

                start_text = sd.strftime("%a, %b %d at %I:%M %p").replace(" 0", " ")

                if end_dt:
                    try:
                        ed = dtparser.isoparse(end_dt)
                        if ed.tzinfo is None:
                            ed = ed.replace(tzinfo=timezone.utc)
                        ed = ed.astimezone()
                        end_text = ed.strftime("%I:%M %p").lstrip("0")
                        when = f"{start_text} - {end_text}"
                    except Exception:
                        when = start_text
                else:
                    when = start_text
            except Exception:
                when = "Date coming soon"

        parts = [title, when]
        if end_dt:
            try:
                ed = dtparser.isoparse(end_dt)
        
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=timezone.utc)
        
                ed = ed.astimezone()
        
                ends_text = ed.strftime("Ends at %-I:%M %p")
        
                parts.append(ends_text)
        
            except Exception:
                pass


        if description:
            parts.append(description)

        if location:
            parts.append(location)

        lines.append("\n".join(parts))

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

    if any(k in m for k in ["weekend", "this weekend", "friday", "saturday"]):
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
        weekday = local_now.weekday()  # Monday=0 ... Sunday=6

        if weekday in [4, 5, 6]:
            # Friday, Saturday, Sunday -> use THIS weekend
            friday = (local_now - timedelta(days=weekday - 4)).date()
        else:
            # Monday-Thursday -> use UPCOMING weekend
            friday = (local_now + timedelta(days=4 - weekday)).date()

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

    if intent == "right_now":
        active = get_right_now_events(events)
    
        if active:
            return active
    
        return []


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
           str(e.get("category", "")),
           str(e.get("description", "")),
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
        "build": "stable-reset-v2-approve",
    })

@app.get("/db-test")
def db_test():
    try:
        return {
            "ok": True,
            "database_url_exists": bool(DATABASE_URL),
            "database_url_starts_with": DATABASE_URL[:20] if DATABASE_URL else "EMPTY"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/events")
def events():
    events = get_all_events()

    return app.response_class(
        response=json.dumps(events, indent=2),
        status=200,
        mimetype="application/json",
    )


def get_right_now_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = now_utc()
    active = []

    for e in events:
        start_dt = e.get("start_dt")
        end_dt = e.get("end_dt")

        if not start_dt or not end_dt:
            continue

        try:
            sd = dtparser.isoparse(start_dt)
            ed = dtparser.isoparse(end_dt)

            if sd.tzinfo is None:
                sd = sd.replace(tzinfo=timezone.utc)
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=timezone.utc)

            if sd <= now <= ed:
                active.append(e)
        except Exception:
            continue

    return active

def load_saved_events():
    try:
        with open(EVENTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_saved_events(events):
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=2)


def save_one_event(event):
    events = load_saved_events()
    events.append(event)
    save_saved_events(events)


def handle_chat():
    global CURRENT_EVENT, CURRENT_EVENTS

    data = request.get_json(silent=True) or {}
    msg = data.get("message", "").lower()


    
    try:
        events = get_all_events()
        events = filter_future_events(events)
        print("CHAT EVENTS COUNT:", len(events))
    except Exception as e:
        print("Events load error:", e)
        events = []
        
    global CURRENT_EVENT, CURRENT_EVENTS

    if any(word in msg for word in [
        "directions",
        "address",
        "where is it",
        "where's it",
        "where is this",
        "location"
    ]) and CURRENT_EVENT:
        return jsonify({
            "message": f"{CURRENT_EVENT.get('title', 'That event')} is at {CURRENT_EVENT.get('location', 'the listed location')}."
        }), 200


    if CURRENT_EVENT:

        if any(x in msg for x in ["cost", "price", "ticket", "admission", "how much"]):
            desc = CURRENT_EVENT.get("description", "")
            title = CURRENT_EVENT.get("title", "That event")
    
            return jsonify({
                "message": f"{title}: {desc}"
            }), 200
    
        if any(x in msg for x in ["time", "start", "when"]):
            dt = CURRENT_EVENT.get("start_dt", "")
    
            try:
                pretty_time = datetime.fromisoformat(dt).strftime("%A, %B %d at %-I:%M %p").replace(" 0", " ")
            except:
                pretty_time = dt
    
            return jsonify({
                "message": f"{CURRENT_EVENT.get('title', 'That event')} starts {pretty_time}."
            }), 200
    
        if any(x in msg for x in ["directions", "get directions", "take me there", "map"]):
            location = CURRENT_EVENT.get("location", "")
    
            return jsonify({
                "message": f"{CURRENT_EVENT.get('title', 'That event')} is at {location}.\n\nCopy this into Google Maps:\n{location}"
            }), 200
    
        if any(x in msg for x in ["where", "location", "address"]):
            return jsonify({
                "message": f"{CURRENT_EVENT.get('title', 'That event')} is at {CURRENT_EVENT.get('location', 'the listed location')}."
            }), 200




    
        if any(x in msg for x in ["where", "location", "address"]):
            return jsonify({
                "message": f"{CURRENT_EVENT.get('title', 'That event')} is at {CURRENT_EVENT.get('location', 'the listed location')}."
            }), 200
    
        if any(x in msg for x in ["description", "details", "tell me more"]):
            return jsonify({
                "message": CURRENT_EVENT.get("description", "No additional details available.")
            }), 200
    
    # Simple intent detection
    intent = "general"
    if "music" in msg:
        intent = "music"
    elif "art" in msg:
        intent = "art"
    elif "family" in msg:
        intent = "family"
    elif "class" in msg:
        intent = "classes"
    elif "today" in msg:
        intent = "today"
    elif "right now" in msg:
        intent = "right_now"    

    scoped = filter_by_intent(events, intent)


    if not scoped:
        reply_body = "I'm not seeing any upcoming events from my current sources."
    else:
        lines = []

        for e in scoped:
            title = e.get("title", "Untitled")
            location = e.get("location", "Location TBD")
            description = e.get("description", "")
    
            start_dt = e.get("start_dt", "")
    
            lines.append(
                f"{title}\n"
                f"{location}\n"
                f"{description}"
            )
    
        reply_body = "\n\n".join(lines)



    # Tone variations
    if intent == "music":
        intro = "Here are some music-related things happening."
        outro = "\n\nWant live bands, acoustic sets, or something bigger?"
    elif intent == "art":
        intro = "Here are a few art-related things worth checking out."
        outro = "\n\nWant gallery openings, classes, or something more casual?"
    elif intent == "family":
        intro = "Here are some family-friendly options that look good."
        outro = "\n\nWant indoor, outdoor, or something quick and easy?"
    elif intent == "classes":
        intro = "Here are some classes and workshops coming up."
        outro = "\n\nWant creative, kid-friendly, or more advanced options?"
    elif intent == "today":
        intro = "Here’s what’s looking good today."
        outro = "\n\nWant me to narrow it to right now, food, or something nearby?"
    else:
        intro = "Here are a few good options I found."
        outro = "\n\nWant me to narrow it down by music, food, family, or art?"

    reply = f"{intro}\n\n{reply_body}{outro}"

    CURRENT_EVENTS = scoped[:5]

    if len(CURRENT_EVENTS) == 1:
        CURRENT_EVENT = CURRENT_EVENTS[0]
    
    if any(x in msg for x in ["tell me more", "more about", "details", "detail"]):
        if scoped:
            CURRENT_EVENT = scoped[0]


    # 🔥 AI LAYER (SAFE WRAPPED)
    try:
        ai_reply = generate_ai_response(msg, scoped, CONVERSATION_HISTORY)
        
        CONVERSATION_HISTORY.append({"role": "user", "content": msg})
        CONVERSATION_HISTORY.append({"role": "assistant", "content": ai_reply})
        
        if len(CONVERSATION_HISTORY) > 10:
            del CONVERSATION_HISTORY[:-10]
    
        if ai_reply:
            return jsonify({"message": ai_reply}), 200
    except Exception as e:
        print("AI wrapper error:", e)

    return jsonify({"message": reply}), 200

    reply_body = format_events(scoped, limit=6)

    if intent == "right_now":
        intro = "There are a few good options happening right now."
        outro = "\n\nWant food, live music, or just the strongest option?"
    elif intent == "weekend":
        intro = "Here are a few solid things happening this weekend."
        outro = "\n\nWant me to narrow it to music, family-friendly, or something more laid-back?"
    elif intent == "music":
        intro = "A couple good music options are standing out."
        outro = "\n\nWant something more chill, bigger energy, or earlier in the night?"
    elif intent == "art":
        intro = "Here are a few art-related things worth checking out."
        outro = "\n\nWant gallery-type stuff, classes, or something more social?"
    elif intent == "family":
        intro = "Here are some family-friendly options that look good."
        outro = "\n\nWant indoor, outdoor, or something easy and low-effort?"
    elif intent == "classes":
        intro = "Here are some classes and workshops coming up."
        outro = "\n\nWant creative, kid-friendly, or more adult-focused options?"
    elif intent == "today":
        intro = "Here’s what’s looking good today."
        outro = "\n\nWant me to narrow it to right now, tonight, food, or music?"
    else:
        intro = "Here are a few good options I found."
        outro = "\n\nWant me to narrow it down by food, music, family, art, or what’s happening right now?"

    reply = f"{intro}\n\n{reply_body}{outro}"

    try:
        ai_reply = generate_ai_response(msg, events)
        if ai_reply:
            return jsonify({"message": ai_reply}), 200
    except Exception as e:
        print("AI wrapper error:", e)
    
    return jsonify({"message": reply}), 200
    
@app.post("/lumi-chat")
def handle_lumi_chat():
    data = request.get_json(silent=True) or {}
    msg = data.get("message", "")

    ai_reply = generate_lumi_response(msg)

    if ai_reply:
        return jsonify({"message": ai_reply}), 200

    return jsonify({
        "message": "Lumi is having a little trouble answering right now. Try again in a moment."
    }), 200

    
@app.post("/fspt-chat")
def handle_fspt_chat():
    data = request.get_json(silent=True) or {}
    msg = data.get("message", "")

    ai_reply = generate_fspt_response(msg)

    if ai_reply:
        return jsonify({"message": ai_reply}), 200

    return jsonify({
        "message": "The First Settlement Physical Therapy Assistant is having a little trouble answering right now. Try again in a moment."
    }), 200

@app.get("/bulk-ingest")
def bulk_ingest():
    html = """
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px;">
        <h2>Bulk Ingest</h2>
        <p>Paste raw event text below.</p>
        <form method="post" action="/bulk-ingest">
            <textarea name="raw_text" rows="18" style="width: 100%; padding: 12px; font-size: 16px;"></textarea>
            <br><br>
            <button type="submit" style="padding: 12px 18px; font-size: 16px;">Preview Raw Text</button>
        </form>
        <br>
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

@app.post("/bulk-ingest")
def bulk_ingest_post():
    raw_text = (request.form.get("raw_text") or "").strip()

    import re

    events = []
    blocks = raw_text.split("Title:")
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
    
        block = "Title:" + block
        event = {}
    
        for line in block.splitlines():
            if ":" not in line:
                continue
    
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
    
            if key == "title":
                event["title"] = value
            elif key == "start date/time":
                event["start_dt"] = value
            elif key == "end date/time":
                event["end_dt"] = value
            elif key == "location":
                event["location"] = value
            elif key == "source":
                event["source"] = value
            elif key == "url":
                event["url"] = value
            elif key == "category":
                event["category"] = value
            elif key == "description":
                event["description"] = value
    
        if event.get("title") and event.get("start_dt"):
            events.append(event)


    hidden_inputs = ""
    for e in events:
        hidden_inputs += f"""
        <input type="hidden" name="title" value="{e.get('title', '')}">
        <input type="hidden" name="start_dt" value="{e.get('start_dt', '')}">
        <input type="hidden" name="end_dt" value="{e.get('end_dt', '')}">
        <input type="hidden" name="location" value="{e.get('location', '')}">
        <input type="hidden" name="source" value="{e.get('source', 'Bulk Import')}">
        <input type="hidden" name="url" value="{e.get('url', '')}">
        <input type="hidden" name="category" value="{e.get('category', '')}">
        <input type="hidden" name="description" value="{e.get('description', '')}">
        """


    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px;">
        <h2>Bulk Ingest Preview</h2>

        <h3>Detected Events</h3>
        <ul>
            {''.join([
                f"<li><strong>{e.get('title', '')}</strong><br>"
                f"Start: {e.get('start_dt', '')}<br>"
                f"End: {e.get('end_dt', '')}<br>"
                f"Location: {e.get('location', '')}<br>"
                f"Category: {e.get('category', '')}<br><br></li>"
                for e in events
            ])}

                
        </ul>

        <form method="post" action="/bulk-ingest-save">
            {hidden_inputs}
            <button type="submit" style="padding: 12px 18px; font-size: 16px;">Send All to Pending</button>
        </form>

        <br><br>
        <a href="/bulk-ingest">Back to Bulk Ingest</a><br>
        <a href="/dashboard">Back to Dashboard</a>
    </body>
    </html>
    """

@app.post("/bulk-ingest-save")
def bulk_ingest_save():

    titles = request.form.getlist("title")
    start_dts = request.form.getlist("start_dt")
    end_dts = request.form.getlist("end_dt")
    locations = request.form.getlist("location")
    sources = request.form.getlist("source")
    urls = request.form.getlist("url")
    categories = request.form.getlist("category")
    descriptions = request.form.getlist("description")

    count = 0

    for i in range(len(titles)):

        event = {
            "title": titles[i],
            "start_dt": start_dts[i],
            "end_dt": end_dts[i],
            "location": locations[i],
            "source": sources[i],
            "url": urls[i],
            "category": categories[i],
            "description": descriptions[i]
        }

        PENDING_EVENTS.append(event)
        count += 1

    save_events_to_file(PENDING_EVENTS_FILE, PENDING_EVENTS)

    return f"""
    <html>
    <body style="font-family: Arial; max-width: 800px; margin: 40px auto;">
        <h2>Bulk Ingest Complete</h2>
        <p>{count} events sent to pending review.</p>

        <p><a href="/review-pending">Review Pending Events</a></p>
        <p><a href="/bulk-ingest">Back to Bulk Ingest</a></p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    """
    
@app.get("/pending-events")
def pending_events():
    return app.response_class(
        response=json.dumps(PENDING_EVENTS, indent=2),
        status=200,
        mimetype="application/json",
    )
    
@app.get("/test-add-brewery-deal")
def test_add_brewery_deal():
    event = {
        "title": "Parkersburg Brewing Co. - $10 cheeseburger special until 10 PM",
        "start_dt": None,
        "location": "Parkersburg Brewing Co., Parkersburg, WV",
        "source": "Manual Test",
        "url": "",
    }

    PENDING_EVENTS.append(event)
    _cache["ts"] = 0

    return {"ok": True, "message": "Brewery deal added to pending"}

def save_event_to_db(event):
    try:
        print("TRYING TO SAVE EVENT:", event)

        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                title TEXT,
                start_dt TEXT,
                end_dt TEXT,
                location TEXT,
                source TEXT,
                url TEXT,
                category TEXT,
                description TEXT
            )
        """)

        cur.execute("""
            INSERT INTO events (title, start_dt, end_dt, location, source, url, category, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            event.get("title"),
            event.get("start_dt"),
            event.get("end_dt"),
            event.get("location"),
            event.get("source"),
            event.get("url"),
            event.get("category"),
            event.get("description"),
        ))

        conn.commit()
        cur.close()
        conn.close()

        print("EVENT SAVED TO DB SUCCESSFULLY")

    except Exception as e:
        print("SAVE EVENT TO DB ERROR:", e)


@app.get("/approve-latest")
def approve_latest():
    if not PENDING_EVENTS:
        return {"ok": False, "message": "No pending events to approve"}, 404

    event = PENDING_EVENTS.pop()
    print("APPROVING EVENT:", event)
    
    APPROVED_EVENTS.append(event)
    
    print("ABOUT TO SAVE TO DB")
    save_event_to_db(event)
    print("FINISHED SAVE TO DB")



    return {"ok": True, "message": "Latest pending event approved", "event": event}

@app.get("/dashboard")
def dashboard():
    html = """
    <!doctype html>
    <html>
    <head>
        <title>Splice AI Dashboard</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background: #f8f8f8;
            }
            h1 {
                margin-bottom: 10px;
            }
            p {
                color: #555;
                margin-bottom: 30px;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
            }
            a.card {
                display: block;
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                text-decoration: none;
                color: #222;
            }
            a.card:hover {
                background: #fff7f7;
            }
            .title {
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 8px;
            }
            .desc {
                color: #666;
                font-size: 14px;
                line-height: 1.4;
            }
        </style>
    </head>
    <body>
        <h1>Splice AI Dashboard</h1>
        <p>Your internal control panel for feeding and reviewing events.</p>

        <div class="grid">
            <a class="card" href="/add-event">
                <div class="title">Add Event</div>
                <div class="desc">Manually enter a new event and send it to pending review.</div>
            </a>

            <a class="card" href="/review-pending">
                <div class="title">Review Pending</div>
                <div class="desc">Approve or reject events waiting to go live.</div>
            </a>

            <a class="card" href="/pending-events">
                <div class="title">Pending JSON</div>
                <div class="desc">Raw view of pending events for debugging.</div>
            </a>

            <a class="card" href="/events">
                <div class="title">Live Events</div>
                <div class="desc">See what is currently live in the feed.</div>
            </a>

            <a class="card" href="/bulk-ingest">
                <div class="title">Bulk Ingest</div>
                <div class="desc">Paste raw text and prep events quickly.</div>
            </a>


            <a class="card" href="/health">
                <div class="title">Health Check</div>
                <div class="desc">Quick status check for the backend service.</div>
            </a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

@app.get("/add-event")
def add_event_form():
    html = """
    <!doctype html>
    <html>
    <head>
        <title>Add Event</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 700px;
                margin: 40px auto;
                padding: 20px;
                background: #f8f8f8;
            }
            h1 {
                margin-bottom: 20px;
            }
            form {
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }
            label {
                display: block;
                margin-top: 15px;
                font-weight: bold;
            }
            input, textarea, select, button {
                width: 100%;
                padding: 10px;
                margin-top: 6px;
                font-size: 16px;
                box-sizing: border-box;
            }
            textarea {
                min-height: 100px;
                resize: vertical;
            }
            button {
                margin-top: 20px;
                background: #e85d5d;
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }
            button:hover {
                background: #d94c4c;
            }
            .note {
                margin-top: 15px;
                color: #666;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <h1>Add Event</h1>
        <form method="post" action="/submit-event-form">
            <label>Title</label>
            <input type="text" name="title" required>

            <label>Start Date/Time</label>
            <input type="text" name="start_dt" placeholder="2026-04-05T18:00:00+00:00">

            <label>End Date/Time</label>
            <input type="text" name="end_dt" placeholder="2026-04-05T22:00:00+00:00">

            <label>Location</label>
            <input type="text" name="location">

            <label>Source</label>
            <input type="text" name="source" value="Manual Entry">

            <label>URL</label>
            <input type="text" name="url">

            <label>Category</label>
            <select name="category">
                <option value="event">Event</option>
                <option value="right_now">Right Now</option>
                <option value="music">Music</option>
                <option value="art">Art</option>
                <option value="family">Family</option>
                <option value="food">Food</option>
                <option value="classes">Classes</option>
            </select>

            <label>Description</label>
            <textarea name="description" placeholder="Short description..."></textarea>

            <button type="submit">Submit to Pending</button>

            <div class="note">
                This sends the event to pending review first.
            </div>
        </form>
    </body>
    </html>
    """
    return render_template_string(html)


@app.post("/submit-event-form")
def submit_event_form():
    title = (request.form.get("title") or "").strip()
    start_dt = (request.form.get("start_dt") or "").strip()
    end_dt = (request.form.get("end_dt") or "").strip()
    location = (request.form.get("location") or "").strip()
    source = (request.form.get("source") or "Manual Entry").strip()
    url = (request.form.get("url") or "").strip()
    category = (request.form.get("category") or "event").strip()
    description = (request.form.get("description") or "").strip()

    if not title:
        return "Title is required", 400

    event = {
        "title": title,
        "start_dt": start_dt or None,
        "end_dt": end_dt or None,
        "location": location,
        "source": source,
        "url": url,
        "category": category,
        "description": description,
    }

    PENDING_EVENTS.append(event)
    save_events_to_file(PENDING_EVENTS_FILE, PENDING_EVENTS)
    _cache["ts"] = 0

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 20px;">
        <h2>Event submitted to pending</h2>
        <p><strong>{title}</strong></p>
        <p><a href="/review-pending">Review Pending Events</a></p>
        <p><a href="/add-event">Add Another Event</a></p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    """

@app.get("/review-pending")
def review_pending():
    html = """
    <!doctype html>
    <html>
    <head>
        <title>Review Pending Events</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 900px;
                margin: 40px auto;
                padding: 20px;
                background: #f8f8f8;
            }
            h1 {
                margin-bottom: 20px;
            }
            .card {
                background: white;
                padding: 18px;
                margin-bottom: 16px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }
            .title {
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .meta {
                margin-bottom: 6px;
                color: #444;
            }
            .buttons {
                margin-top: 15px;
                display: flex;
                gap: 10px;
            }
            button {
                padding: 10px 16px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 15px;
            }
            .approve {
                background: #2e8b57;
                color: white;
            }
            .reject {
                background: #c94c4c;
                color: white;
            }
            .empty {
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }
        </style>
    </head>
    <body>
        <h1>Pending Events Review</h1>
        {% if events %}
            {% for event in events %}
                <div class="card">
                    <div class="title">{{ event.title }}</div>
                    <div class="meta"><strong>Start:</strong> {{ event.start_dt or "None" }}</div>
                    <div class="meta"><strong>Location:</strong> {{ event.location or "None" }}</div>
                    <div class="meta"><strong>Source:</strong> {{ event.source or "None" }}</div>
                    <div class="meta"><strong>URL:</strong> {{ event.url or "None" }}</div>

                    <div class="buttons">
                        <form method="post" action="/approve-pending/{{ loop.index0 }}">
                            <button class="approve" type="submit">Approve</button>
                        </form>

                        <form method="post" action="/reject-pending/{{ loop.index0 }}">
                            <button class="reject" type="submit">Reject</button>
                        </form>
                    </div>
                </div>
            {% endfor %}
        {% else %}
            <div class="empty">No pending events right now.</div>
        {% endif %}
    </body>
    </html>
    """
    return render_template_string(html, events=PENDING_EVENTS)


@app.post("/approve-pending/<int:event_index>")
def approve_pending(event_index: int):
    if event_index < 0 or event_index >= len(PENDING_EVENTS):
        return "Pending event not found", 404

    event = PENDING_EVENTS.pop(event_index)
    APPROVED_EVENTS.append(event)
    save_event_to_db(event)

    _cache["ts"] = 0

    return """
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 20px;">
        <h2>Event approved</h2>
        <p><a href="/review-pending">Back to Pending Review</a></p>
        <p><a href="/events">View Live Events</a></p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    """

@app.post("/reject-pending/<int:event_index>")
def reject_pending(event_index: int):
    if event_index < 0 or event_index >= len(PENDING_EVENTS):
        return "Pending event not found", 404

    PENDING_EVENTS.pop(event_index)
    save_events_to_file(PENDING_EVENTS_FILE, PENDING_EVENTS)
    _cache["ts"] = 0


    return """
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 20px;">
        <h2>Event rejected</h2>
        <p><a href="/review-pending">Back to Pending Review</a></p>
    </body>
    </html>
    """
@app.get("/approved-events")
def approved_events():
    return app.response_class(
        response=json.dumps(APPROVED_EVENTS, indent=2),
        status=200,
        mimetype="application/json",
    )

@app.post("/submit-event")
def submit_event():
    data = request.get_json(force=True)

    title = (data.get("title") or "").strip()
    start_dt = (data.get("start_dt") or "").strip()
    end_dt = (data.get("end_dt") or "").strip()
    location = (data.get("location") or "").strip()
    url = (data.get("url") or "").strip()
    source = (data.get("source") or "Pending Submission").strip()
    category = (data.get("category") or "event").strip()
    description = (data.get("description") or "").strip()

    if not title:
        return jsonify({"ok": False, "error": "title is required"}), 400

    event = {
        "title": title,
        "start_dt": start_dt or None,
        "end_dt": end_dt or None,
        "location": location,
        "source": source,
        "url": url,
        "category": category,
        "description": description,
    }

    PENDING_EVENTS.append(event)
    _cache["ts"] = 0

    return jsonify({"ok": True, "event": event}), 200  

@app.post("/chat")
def chat():
    return handle_chat()

@app.post("/el-chat/chat")
def el_chat_chat():
    return handle_chat()
    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
