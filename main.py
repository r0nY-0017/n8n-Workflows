"""
Bamboo Dine — Restaurant Booking System
FastAPI Backend

Install:  pip install fastapi uvicorn python-multipart httpx jinja2 python-dotenv
Run:      uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv
import httpx, json, re, os
from datetime import datetime

load_dotenv()

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD")
N8N_CHECK_URL   = os.getenv("N8N_CHECK_URL")
N8N_BOOKING_URL = os.getenv("N8N_BOOKING_URL")
N8N_CANCEL_URL  = os.getenv("N8N_CANCEL_URL")
N8N_LIST_URL    = os.getenv("N8N_LIST_URL")
N8N_UPDATE_URL  = os.getenv("N8N_UPDATE_URL")

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY নেই। .env ফাইলে সেট করুন।")
if not ADMIN_PASSWORD:
    raise RuntimeError("❌ ADMIN_PASSWORD নেই। .env ফাইলে সেট করুন।")

# ─────────────────────────────────────────────
#  RESTAURANT INFO
# ─────────────────────────────────────────────
RESTAURANT_INFO = {
    "name":     "Bamboo Dine",
    "address":  "ধানমন্ডি ২৭, ঢাকা-১২০৫",
    "phone":    "01700-11223344",
    "email":    "info@bamboodine.com",
    "hours":    "সন্ধ্যা ৬টা – রাত ১১টা (শনি–বৃহস্পতি)",
    "tables":   6,
    "slots":    ["18:00","19:00","20:00","21:00","22:00","23:00"],
    "capacity_per_slot": 6,
}

ALL_TABLES = ["T-1", "T-2", "T-3", "T-4", "T-5", "T-6"]

MENU_INFO = """
🍛 বিরিয়ানি ও পোলাও:
  • কাচ্চি বিরিয়ানি — ৳৩৮০
  • মোরগ পোলাও — ৳৩২০

🐟 মাছ:
  • ইলিশ ভাপা — ৳৪৫০
  • চিংড়ি মালাইকারি — ৳৫২০
  • রুই মাছের ঝোল — ৳২৮০

🥩 মাংস:
  • খাসির রেজালা — ৳৪৮০
  • মাটন রোস্ট — ৳৫৫০
  • চিকেন রেজালা — ৳৩২০

🥗 ভর্তা ও সবজি:
  • ভর্তা থালি (৭ রকম) — ৳২২০
  • শাক ঘণ্ট — ৳১৮০

🍮 মিষ্টি:
  • রসমালাই — ৳১২০
  • পায়েস — ৳১০০

🌟 আজকের স্পেশাল:
  • ফ্যামিলি কাচ্চি প্যাকেজ (৪ জন) — ৳১,৮০০
  • ইলিশ উৎসব থালি — ৳৮৫০
  • বার্থডে ডিনার প্যাকেজ — ৳৩,৫০০
"""

SYSTEM_PROMPT = f"""তুমি "Bamboo Dine" রেস্তোরাঁর AI সহকারী "Bamboo AI"।
বাংলায় কথা বলো। উষ্ণ ও আন্তরিক থাকো।

== রেস্তোরাঁর তথ্য ==
নাম: {RESTAURANT_INFO['name']}
ঠিকানা: {RESTAURANT_INFO['address']}
ফোন: {RESTAURANT_INFO['phone']}
খোলার সময়: {RESTAURANT_INFO['hours']}
টেবিল: T-1 থেকে T-6 (মোট ৬টি)
বুকিং স্লট: সন্ধ্যা ৬টা থেকে রাত ১১টা (প্রতি ঘণ্টা)

== মেনু ==
{MENU_INFO}

== বুকিং Flow (ধাপে ধাপে অনুসরণ করো) ==

ধাপ ১ — তারিখ, সময়, কতজন জিজ্ঞেস করো।

ধাপ ২ — availability check করো (এই tag লেখো):
  ##CHECK##{{"date":"YYYY-MM-DD","time":"HH:00"}}##END##
  system তোমাকে [SYSTEM: খালি টেবিল: T-X, T-Y...] আকারে জানাবে।

ধাপ ৩ — খালি টেবিলগুলো customer-কে দেখাও, choose করতে বলো।
  উদাহরণ: "এই সময়ে T-2, T-4 এবং T-6 খালি আছে। কোন টেবিলটি পছন্দ করবেন?"
  যদি কোনো টেবিল না থাকে → অন্য সময় suggest করো।

ধাপ ৪ — customer টেবিল choose করলে → নাম, ফোন, ইমেইল নাও।

ধাপ ৫ — সব তথ্য পেলে booking confirm করো:
  ##BOOKING##{{"name":"...","phone":"...","email":"...","date":"YYYY-MM-DD","time":"HH:00","guests":N,"table":"T-X"}}##END##

== বুকিং বাতিল ==
  - Booking ID জিজ্ঞেস করো
  - confirm চাও
  - confirm হলে: ##CANCEL##{{"booking_id":"..."}}##END##

== নিয়ম ==
- ৬ জনের বেশি হলে ফোনে যোগাযোগ করতে বলো: {RESTAURANT_INFO['phone']}
- Customer নির্দিষ্ট টেবিল না চাইলে → খালি টেবিলের মধ্যে প্রথমটি suggest করো।
- অন্য বিষয়ে: "এই বিষয়ে আমি সাহায্য করতে পারব না, তবে বুকিং বা রেস্তোরাঁ সম্পর্কে যেকোনো প্রশ্ন করুন।"
"""

# ─────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────
app = FastAPI(title="Bamboo Dine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

class AdminLoginRequest(BaseModel):
    password: str

class ManualBookingRequest(BaseModel):
    name: str
    phone: str
    email: Optional[str] = ""
    date: str
    time: str
    guests: int
    table: Optional[str] = ""
    notes: Optional[str] = ""

class CancelRequest(BaseModel):
    booking_id: str

class UpdateBookingRequest(BaseModel):
    booking_id: str
    name:     Optional[str] = None
    phone:    Optional[str] = None
    email:    Optional[str] = None
    date:     Optional[str] = None
    time:     Optional[str] = None
    table:    Optional[str] = None
    guests:   Optional[int] = None
    status:   Optional[str] = None
    notes:    Optional[str] = None

# ─────────────────────────────────────────────
#  N8N HELPERS
# ─────────────────────────────────────────────
async def n8n_check_availability(date: str, time: str) -> dict:
    """n8n → Google Sheets availability check
    Returns: {available, booked_count, free_tables: ["T-1","T-2",...], free_count}
    """
    if not N8N_CHECK_URL:
        return {
            "available":   True,
            "booked_count": 0,
            "free_tables": ALL_TABLES.copy(),
            "free_count":  6,
        }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(N8N_CHECK_URL, json={"date": date, "time": time})
            data = resp.json()

        # n8n থেকে free_tables না আসলে booked_count থেকে calculate করি
        if "free_tables" not in data:
            booked = data.get("booked_count", 0)
            data["free_tables"] = ALL_TABLES[booked:]
            data["free_count"]  = max(0, 6 - booked)

        return data
    except Exception as e:
        print(f"[n8n check] error: {e}")
        return {
            "available":   True,
            "booked_count": 0,
            "free_tables": ALL_TABLES.copy(),
            "free_count":  6,
        }

async def n8n_save_booking(booking: dict) -> dict:
    if not N8N_BOOKING_URL:
        print("[n8n booking] URL not set — skipping")
        return {"success": True}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(N8N_BOOKING_URL, json={"booking": booking})
            return resp.json()
    except Exception as e:
        print(f"[n8n booking] error: {e}")
        return {"success": False, "error": str(e)}

async def n8n_cancel_booking(booking_id: str) -> dict:
    if not N8N_CANCEL_URL:
        print("[n8n cancel] URL not set — skipping")
        return {"success": True}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(N8N_CANCEL_URL, json={"booking_id": booking_id})
            return resp.json()
    except Exception as e:
        print(f"[n8n cancel] error: {e}")
        return {"success": False, "error": str(e)}

def make_booking_id() -> str:
    import uuid
    return "BD" + str(uuid.uuid4())[:6].upper()

# ─────────────────────────────────────────────
#  PAGES
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────
@app.post("/api/admin/login")
async def admin_login(body: AdminLoginRequest):
    if body.password == ADMIN_PASSWORD:
        return {"success": True, "token": "bd-admin-token"}
    raise HTTPException(status_code=401, detail="ভুল পাসওয়ার্ড")

# ─────────────────────────────────────────────
#  CHAT
# ─────────────────────────────────────────────
@app.post("/api/chat")
async def chat(body: ChatRequest):
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *[{"role": m.role, "content": m.content} for m in body.messages],
                    ],
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=data.get("error", {}).get("message", "OpenAI error"),
                )

        reply  = data["choices"][0]["message"]["content"]
        result = {"reply": "", "action": None}

        # ── CHECK tag ──
        check_match = re.search(r"##CHECK##(.*?)##END##", reply, re.DOTALL)
        if check_match:
            try:
                raw          = json.loads(check_match.group(1).strip())
                avail        = await n8n_check_availability(raw["date"], raw["time"])
                free_tables  = avail.get("free_tables", [])
                booked_count = avail.get("booked_count", 0)
                is_avail     = booked_count < RESTAURANT_INFO["capacity_per_slot"]

                result["action"] = {
                    "type":        "availability",
                    "date":        raw["date"],
                    "time":        raw["time"],
                    "available":   is_avail,
                    "free_tables": free_tables,
                    "remaining":   len(free_tables),
                }

                # free_tables পেয়ে আবার OpenAI call — AI এবার সঠিক table নাম বলবে
                table_info = (
                    f"[SYSTEM RESULT: {raw['date']} তারিখ {raw['time']}-এ "
                    f"খালি টেবিল: {', '.join(free_tables)}। "
                    f"এখন customer-কে এই টেবিলগুলো দেখাও এবং কোনটি নেবেন জিজ্ঞেস করো।]"
                ) if free_tables else (
                    f"[SYSTEM RESULT: {raw['date']} তারিখ {raw['time']}-এ কোনো টেবিল খালি নেই। অন্য সময় suggest করো।]"
                )

                updated_messages = [
                    {"role": "system",    "content": SYSTEM_PROMPT},
                    *[{"role": m.role, "content": m.content} for m in body.messages],
                    {"role": "assistant", "content": re.sub(r"##CHECK##.*?##END##", "", reply, flags=re.DOTALL).strip()},
                    {"role": "user",      "content": table_info},
                ]

                async with httpx.AsyncClient(timeout=30) as c2:
                    resp2 = await c2.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                        json={"model": "gpt-4o-mini", "messages": updated_messages, "max_tokens": 400, "temperature": 0.7},
                    )
                    reply2 = resp2.json()["choices"][0]["message"]["content"]

                result["reply"] = reply2
                return result

            except Exception as e:
                print(f"[check parse] {e}")

        # ── BOOKING tag ──
        booking_match = re.search(r"##BOOKING##(.*?)##END##", reply, re.DOTALL)
        if booking_match:
            try:
                raw          = json.loads(booking_match.group(1).strip())
                chosen_table = raw.get("table", "")

                # Final check — chosen table এখনও খালি কিনা
                avail       = await n8n_check_availability(raw["date"], raw["time"])
                free_tables = avail.get("free_tables", [])

                if not free_tables:
                    clean = re.sub(r"##BOOKING##.*?##END##", "", reply, flags=re.DOTALL).strip()
                    result["reply"] = (
                        clean + f"\n\nদুঃখিত, {raw['date']} তারিখ "
                        f"{raw['time']}-এ আর কোনো টেবিল খালি নেই। অন্য সময় চেষ্টা করুন।"
                    )
                    return result

                # chosen table বুকড হয়ে গেলে প্রথম free table দাও
                if not chosen_table or chosen_table not in free_tables:
                    chosen_table = free_tables[0]

                booking = {
                    "id":         make_booking_id(),
                    "name":       raw["name"],
                    "phone":      raw["phone"],
                    "email":      raw.get("email", ""),
                    "date":       raw["date"],
                    "time":       raw["time"],
                    "table":      chosen_table,
                    "guests":     raw["guests"],
                    "status":     "confirmed",
                    "source":     "online",
                    "notes":      "",
                    "created_at": datetime.now().isoformat(),
                }
                await n8n_save_booking(booking)
                result["action"] = {"type": "booking_confirmed", "booking": booking}

            except Exception as e:
                print(f"[booking parse] {e}")

        # ── CANCEL tag ──
        cancel_match = re.search(r"##CANCEL##(.*?)##END##", reply, re.DOTALL)
        if cancel_match:
            try:
                raw           = json.loads(cancel_match.group(1).strip())
                cancel_result = await n8n_cancel_booking(raw["booking_id"])
                result["action"] = {
                    "type":       "booking_cancelled",
                    "booking_id": raw["booking_id"],
                    "success":    cancel_result.get("success", False),
                }
            except Exception as e:
                print(f"[cancel parse] {e}")

        clean = re.sub(r"##(CHECK|BOOKING|CANCEL)##.*?##END##", "", reply, flags=re.DOTALL).strip()
        result["reply"] = clean
        return result

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenAI timeout")


# ─────────────────────────────────────────────
#  AVAILABILITY  (admin dashboard)
# ─────────────────────────────────────────────
@app.get("/api/availability")
async def get_availability(date: str):
    slots = []
    for slot in RESTAURANT_INFO["slots"]:
        avail       = await n8n_check_availability(date, slot)
        booked      = avail.get("booked_count", 0)
        free_tables = avail.get("free_tables", ALL_TABLES[booked:])
        total       = RESTAURANT_INFO["capacity_per_slot"]
        slots.append({
            "time":        slot,
            "booked":      booked,
            "total":       total,
            "available":   booked < total,
            "free_tables": free_tables,
        })
    return {"date": date, "slots": slots}


# ─────────────────────────────────────────────
#  BOOKINGS  (admin)
# ─────────────────────────────────────────────
@app.get("/api/bookings")
async def get_bookings(date: str = "", search: str = "", status: str = "all"):
    if not N8N_LIST_URL:
        return {"bookings": [], "total": 0, "note": "N8N_LIST_URL not set"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(N8N_LIST_URL, json={"date": date, "search": search, "status": status})
            data = resp.json()
            return {"bookings": data.get("bookings", []), "total": data.get("total", 0)}
    except Exception as e:
        return {"bookings": [], "total": 0, "error": str(e)}


@app.post("/api/bookings")
async def create_manual_booking(body: ManualBookingRequest):
    avail       = await n8n_check_availability(body.date, body.time)
    free_tables = avail.get("free_tables", [])

    if not free_tables:
        raise HTTPException(status_code=409, detail="এই সময়ে কোনো টেবিল খালি নেই")

    chosen_table = body.table or ""
    if chosen_table and chosen_table not in free_tables:
        raise HTTPException(
            status_code=409,
            detail=f"{chosen_table} ইতিমধ্যে বুকড। খালি টেবিল: {', '.join(free_tables)}",
        )
    if not chosen_table:
        chosen_table = free_tables[0]

    booking = {
        "id":         make_booking_id(),
        "name":       body.name,
        "phone":      body.phone,
        "email":      body.email or "",
        "date":       body.date,
        "time":       body.time,
        "table":      chosen_table,
        "guests":     body.guests,
        "status":     "confirmed",
        "source":     "manual",
        "notes":      body.notes or "",
        "created_at": datetime.now().isoformat(),
    }
    await n8n_save_booking(booking)
    return {"success": True, "booking": booking}


@app.post("/api/bookings/cancel")
async def cancel_booking(body: CancelRequest):
    result = await n8n_cancel_booking(body.booking_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Cancel failed"))
    return {"success": True}


@app.post("/api/bookings/update")
async def update_booking(body: UpdateBookingRequest):
    """Admin বা chatbot — যেকোনো field update করতে পারবে"""
    update_url = os.getenv("N8N_UPDATE_URL")
    if not update_url:
        raise HTTPException(status_code=503, detail="N8N_UPDATE_URL not set in .env")
    try:
        payload = {"booking_id": body.booking_id}
        if body.name    is not None: payload["name"]   = body.name
        if body.phone   is not None: payload["phone"]  = body.phone
        if body.email   is not None: payload["email"]  = body.email
        if body.date    is not None: payload["date"]   = body.date
        if body.time    is not None: payload["time"]   = body.time
        if body.table   is not None: payload["table"]  = body.table
        if body.guests  is not None: payload["guests"] = body.guests
        if body.status  is not None: payload["status"] = body.status
        if body.notes   is not None: payload["notes"]  = body.notes
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(update_url, json=payload)
            result = resp.json()
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Update failed"))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  STATS  (admin dashboard)
# ─────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    from datetime import date
    today = date.today().isoformat()
    if not N8N_LIST_URL:
        return {"today": 0, "total": 0, "confirmed": 0, "cancelled": 0}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            all_resp   = await c.post(N8N_LIST_URL, json={"status": "all"})
            today_resp = await c.post(N8N_LIST_URL, json={"date": today, "status": "all"})
        all_data   = all_resp.json().get("bookings", [])
        today_data = today_resp.json().get("bookings", [])
        return {
            "total":     len(all_data),
            "today":     len(today_data),
            "confirmed": sum(1 for b in all_data if b.get("status") == "confirmed"),
            "cancelled": sum(1 for b in all_data if b.get("status") == "cancelled"),
        }
    except Exception as e:
        return {"today": 0, "total": 0, "confirmed": 0, "cancelled": 0, "error": str(e)}