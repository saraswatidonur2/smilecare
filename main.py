# STEP 3: slot hold (5 min) + test payment + booking only after payment + calendar invite.
import random, time, uuid
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

app = FastAPI()
DEMO_MODE = True        # OTP shown on screen; payment is simulated
HOLD_SECONDS = 300      # a slot is held for 5 minutes while the patient pays
AMOUNT = 500            # consultation fee in rupees

SLOTS = [
    {"id": 1, "doctor": "Dr. Rao",   "date": "Sat", "time": "10:00 AM", "booked": False},
    {"id": 2, "doctor": "Dr. Rao",   "date": "Sat", "time": "11:00 AM", "booked": False},
    {"id": 3, "doctor": "Dr. Meena", "date": "Sat", "time": "09:30 AM", "booked": False},
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

# ---------- routes ----------
@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/chat")
def chat(data: ChatIn):
    text = data.message.lower()
    # TODO (next step): replace with a Claude API call + tools
    if "clean" in text or "book" in text or "appointment" in text:
        free = [s for s in SLOTS if slot_free(s)]
        if not free:
            return {"reply": "Sorry, no slots are free right now. Please try again in a few minutes.", "ui": None}
        return {"reply": "Here are the available slots:", "ui": {"type": "slots", "slots": free}}
    return {"reply": "I can help you book. Try: cleaning on Saturday morning", "ui": None}

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
    ORDERS[order_id] = {"slot_id": data.slot_id, "name": data.name, "mobile": data.mobile, "status": "created"}
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
            "reply": f"Payment received. Confirmed! {order['name']}, {slot['doctor']} on {when.strftime('%a %d %b')} at {slot['time']}. Receipt: {data.order_id}"}

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
        f"SUMMARY:Dental appointment with {slot['doctor']}", "LOCATION:SmileCare Dental Clinic",
        "END:VEVENT", "END:VCALENDAR", ""])
    return Response(ics, media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="appointment.ics"'})
