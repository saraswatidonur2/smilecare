# STEP 5: embeddable widget (/widget.js), sample clinic site (/site), doctor dashboard (/dashboard), plus Steps 1-4.
import os, random, re, time, uuid
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

app = FastAPI()
DEMO_MODE = True        # OTP shown on screen; payment is simulated
DASHBOARD_KEY = os.environ.get("DASHBOARD_KEY", "demo123")   # simple access key for the doctor dashboard
HOLD_SECONDS = 300      # a slot is held for 5 minutes while the patient pays
AMOUNT = 500            # consultation fee in rupees

SLOTS = [
    {"id": 1, "doctor": "Dr. Rao",   "date": "Mon", "time": "10:00 AM", "booked": False},
    {"id": 2, "doctor": "Dr. Rao",   "date": "Mon", "time": "05:00 PM", "booked": False},
    {"id": 3, "doctor": "Dr. Rao",   "date": "Wed", "time": "11:00 AM", "booked": False},
    {"id": 4, "doctor": "Dr. Rao",   "date": "Sat", "time": "10:00 AM", "booked": False},
    {"id": 5, "doctor": "Dr. Rao",   "date": "Sat", "time": "11:00 AM", "booked": False},
    {"id": 6, "doctor": "Dr. Meena", "date": "Tue", "time": "09:30 AM", "booked": False},
    {"id": 7, "doctor": "Dr. Meena", "date": "Fri", "time": "04:30 PM", "booked": False},
    {"id": 8, "doctor": "Dr. Meena", "date": "Sat", "time": "09:30 AM", "booked": False},
    {"id": 9, "doctor": "Dr. Meena", "date": "Sat", "time": "05:30 PM", "booked": False},
]
OTPS = {}       # mobile -> {otp, expires, tries}
VERIFIED = set()
HOLDS = {}      # slot_id -> {mobile, expires}
ORDERS = {}     # order_id -> {slot_id, name, mobile, status}

class ChatIn(BaseModel):
    message: str
class OtpIn(BaseModel):
    slot_id: int
    mobile: str
class VerifyIn(BaseModel):
    mobile: str
    otp: str
class OrderIn(BaseModel):
    slot_id: int
    name: str
    mobile: str
    service: str = "Dental visit"
class PayIn(BaseModel):
    order_id: str
    success: bool

# ---------- helpers ----------
def get_slot(slot_id):
    return next((s for s in SLOTS if s["id"] == slot_id), None)

def held_by_other(slot_id, mobile=None):
    """True if someone else currently holds this slot."""
    h = HOLDS.get(slot_id)
    if not h:
        return False
    if time.time() > h["expires"]:
        HOLDS.pop(slot_id, None)
        return False
    return mobile is None or h["mobile"] != mobile

def holds_valid(slot_id, mobile):
    h = HOLDS.get(slot_id)
    return bool(h and h["mobile"] == mobile and time.time() <= h["expires"])

def slot_free(slot, mobile=None):
    return (not slot["booked"]) and (not held_by_other(slot["id"], mobile))

DAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
def appointment_start(slot):
    """Next real date for the slot's weekday and time."""
    now = datetime.now()
    ahead = (DAYS[slot["date"]] - now.weekday()) % 7 or 7
    day = now + timedelta(days=ahead)
    t = datetime.strptime(slot["time"], "%I:%M %p")
    return day.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


# ---------- understanding free text (no AI key needed) ----------
SERVICES = {
    "Cleaning": ["clean", "scaling", "polish"],
    "Checkup": ["checkup", "check-up", "check up", "consult", "exam"],
    "Filling": ["filling", "cavity", "cavities"],
    "Root canal": ["root canal", "rct"],
    "Extraction": ["extract", "tooth removal", "pull out"],
    "Braces consultation": ["brace", "aligner", "straighten"],
    "Whitening": ["whiten"],
}
EMERGENCY = ["severe pain", "bleeding", "swelling", "swollen", "emergency", "accident", "knocked out", "can't breathe", "unbearable"]
DAY_WORDS = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def find_service(text):
    for name, words in SERVICES.items():
        if any(w in text for w in words):
            return name
    return None

def find_doctor(text):
    for d in {s["doctor"] for s in SLOTS}:
        if d.lower().split()[-1] in text:          # "rao", "meena"
            return d
    return None

def find_day(text):
    if "tomorrow" in text:
        return WEEKDAY_NAMES[(datetime.now().weekday() + 1) % 7]
    if "weekend" in text:
        return "Sat"
    for word in re.findall(r"[a-z]+", text):
        if word[:3] in DAY_WORDS and (len(word) == 3 or word in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday","tues","thur","thurs","weds")):
            return DAY_WORDS[word[:3]]
    return None

def find_part_of_day(text):
    for part in ("morning", "afternoon", "evening"):
        if part in text:
            return part
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        return "hour:%d" % hour
    return None

def part_of(slot):
    hour = datetime.strptime(slot["time"], "%I:%M %p").hour
    return "morning" if hour < 12 else "afternoon" if hour < 16 else "evening"

def matches(slot, doctor, day, part):
    if doctor and slot["doctor"] != doctor: return False
    if day and slot["date"] != day: return False
    if part:
        hour = datetime.strptime(slot["time"], "%I:%M %p").hour
        if part.startswith("hour:"):
            if hour != int(part.split(":")[1]): return False
        elif part_of(slot) != part: return False
    return True

def understand(text):
    return {"service": find_service(text), "doctor": find_doctor(text),
            "day": find_day(text), "part": find_part_of_day(text)}

# ---------- routes ----------
@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/widget.js")
def widget_js():
    return FileResponse("widget.js", media_type="application/javascript")

@app.get("/site")
def sample_site():
    return FileResponse("site.html")

@app.get("/dashboard")
def dashboard_page():
    return FileResponse("dashboard.html")

@app.get("/api/appointments")
def appointments(key: str = "", doctor: str = ""):
    if key != DASHBOARD_KEY:
        return {"ok": False, "reply": "Wrong or missing key."}
    rows = []
    for order_id, o in ORDERS.items():
        if o["status"] != "paid":
            continue
        slot = get_slot(o["slot_id"])
        if doctor and slot["doctor"] != doctor:
            continue
        when = appointment_start(slot)
        rows.append({"sort": when.isoformat(), "order_id": order_id, "patient": o["name"], "service": o["service"],
                     "doctor": slot["doctor"], "date": when.strftime("%a %d %b"), "time": slot["time"],
                     "mobile": "XXXXXX" + o["mobile"][-4:], "status": f"Paid ₹{AMOUNT}"})
    rows.sort(key=lambda r: r["sort"])
    return {"ok": True, "doctors": sorted({s["doctor"] for s in SLOTS}), "appointments": rows}

@app.post("/chat")
def chat(data: ChatIn):
    text = data.message.lower()
    # Urgent symptoms: do not book, send the patient to real help (emergency handoff)
    if any(w in text for w in EMERGENCY):
        return {"reply": "This sounds urgent. Please call the clinic directly or go to the nearest hospital now. I can't treat emergencies in this chat.", "ui": None}
    want = understand(text)
    booking_words = ["book", "appointment", "slot", "schedule", "visit", "see "]
    if not (want["service"] or want["doctor"] or want["day"] or want["part"] or any(w in text for w in booking_words)):
        return {"reply": "I can book your dental visit. Try: cleaning with Dr. Rao on Saturday morning", "ui": None}

    free = [s for s in SLOTS if slot_free(s)]
    service = want["service"] or "Dental visit"
    # exact match first, then relax one condition at a time (smart alternatives)
    tries = [
        (want["doctor"], want["day"], want["part"], ""),
        (want["doctor"], want["day"], None, "No exact time match, but here are other times that day."),
        (want["doctor"], None, None, "No slots on that day, but here are this doctor's other days."),
        (None, want["day"], want["part"], "That doctor isn't free then, but others are."),
        (None, None, None, "I couldn't match everything, so here are the nearest options."),
    ]
    for doctor, day, part, note in tries:
        found = [s for s in free if matches(s, doctor, day, part)]
        if found:
            break
    if not found:
        return {"reply": "Sorry, no slots are free right now. Please try again in a few minutes.", "ui": None}
    summary = service + (f" with {want['doctor']}" if want["doctor"] else "")
    if want["day"]: summary += f" on {want['day']}"
    if want["part"] and not want["part"].startswith("hour:"): summary += f" ({want['part']})"
    reply = f"{note} {summary}: pick a slot." if note else f"{summary}: available slots."
    return {"reply": reply.strip(), "ui": {"type": "slots", "slots": found[:6], "service": service}}

@app.post("/send-otp")
def send_otp(data: OtpIn):
    slot = get_slot(data.slot_id)
    if not slot or not slot_free(slot, data.mobile):
        return {"ok": False, "reply": "Sorry, that slot is no longer available."}
    if not (data.mobile.isdigit() and len(data.mobile) == 10):
        return {"ok": False, "reply": "Please enter a valid 10-digit mobile number."}
    otp = str(random.randint(100000, 999999))
    OTPS[data.mobile] = {"otp": otp, "expires": time.time() + 300, "tries": 0}
    HOLDS[slot["id"]] = {"mobile": data.mobile, "expires": time.time() + HOLD_SECONDS}   # hold the slot
    reply = f"OTP sent to {data.mobile}. Slot held for 5 minutes."
    if DEMO_MODE:
        reply += f" (Demo mode: your OTP is {otp})"
    return {"ok": True, "reply": reply}

@app.post("/verify-otp")
def verify_otp(data: VerifyIn):
    rec = OTPS.get(data.mobile)
    if not rec or time.time() > rec["expires"]:
        return {"ok": False, "reply": "OTP expired. Please start again."}
    rec["tries"] += 1
    if rec["tries"] > 3:
        OTPS.pop(data.mobile, None)
        return {"ok": False, "reply": "Too many wrong attempts. Please start again."}
    if data.otp != rec["otp"]:
        return {"ok": False, "reply": "Wrong OTP. Try again."}
    VERIFIED.add(data.mobile)
    OTPS.pop(data.mobile, None)
    return {"ok": True, "reply": "Mobile verified."}

@app.post("/create-order")
def create_order(data: OrderIn):
    slot = get_slot(data.slot_id)
    if data.mobile not in VERIFIED:
        return {"ok": False, "reply": "Please verify your mobile number first."}
    if not slot or slot["booked"]:
        return {"ok": False, "reply": "Sorry, that slot was just taken."}
    if not holds_valid(data.slot_id, data.mobile):
        return {"ok": False, "reply": "Your 5-minute slot hold expired. Please start again."}
    order_id = "ord_" + uuid.uuid4().hex[:8]
    ORDERS[order_id] = {"slot_id": data.slot_id, "name": data.name, "mobile": data.mobile,
                        "service": data.service, "status": "created"}
    return {"ok": True, "order_id": order_id, "amount": AMOUNT,
            "reply": f"Please pay ₹{AMOUNT} to confirm your appointment."}

@app.post("/pay-demo")
def pay_demo(data: PayIn):
    # Real version: Razorpay calls a webhook on payment success; verify its signature, then run the code below.
    order = ORDERS.get(data.order_id)
    if not order:
        return {"ok": False, "reply": "Order not found."}
    slot = get_slot(order["slot_id"])
    if order["status"] == "paid":                       # idempotent: repeat calls never double-book
        return {"ok": True, "reply": "Already confirmed.", "order_id": data.order_id}
    if not data.success:
        order["status"] = "failed"
        if holds_valid(order["slot_id"], order["mobile"]):
            return {"ok": False, "retry": True, "reply": "Payment failed. Your slot is still held, please try again."}
        return {"ok": False, "reply": "Payment failed and your slot hold expired. Please start again."}
    if slot["booked"] or not holds_valid(order["slot_id"], order["mobile"]):
        return {"ok": False, "reply": "Your slot hold expired. Please start again."}
    slot["booked"] = True                               # booked ONLY after payment succeeds
    order["status"] = "paid"
    HOLDS.pop(order["slot_id"], None)
    VERIFIED.discard(order["mobile"])
    when = appointment_start(slot)
    return {"ok": True, "order_id": data.order_id,
            "reply": f"Payment received. Confirmed! {order['name']}, {order['service']} with {slot['doctor']} on {when.strftime('%a %d %b')} at {slot['time']}. Receipt: {data.order_id}"}

@app.get("/calendar/{order_id}")
def calendar(order_id: str):
    order = ORDERS.get(order_id)
    if not order or order["status"] != "paid":
        return Response("Not found", status_code=404)
    slot = get_slot(order["slot_id"])
    start = appointment_start(slot)
    end = start + timedelta(minutes=30)
    f = "%Y%m%dT%H%M%S"
    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SmileCare//EN", "BEGIN:VEVENT",
        f"UID:{order_id}@smilecare", f"DTSTAMP:{datetime.utcnow().strftime(f)}Z",
        f"DTSTART:{start.strftime(f)}", f"DTEND:{end.strftime(f)}",
        f"SUMMARY:{order['service']} with {slot['doctor']}", "LOCATION:SmileCare Dental Clinic",
        "END:VEVENT", "END:VCALENDAR", ""])
    return Response(ics, media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="appointment.ics"'})
