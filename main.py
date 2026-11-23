# STEP 2: adds OTP verification. The backend refuses to book unless the mobile is verified.
import random, time
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()
DEMO_MODE = True            # True = OTP is shown on screen (no real SMS). Set False when you add a real SMS service.

SLOTS = [
    {"id": 1, "doctor": "Dr. Rao",   "date": "Sat", "time": "10:00 AM", "booked": False},
    {"id": 2, "doctor": "Dr. Rao",   "date": "Sat", "time": "11:00 AM", "booked": False},
    {"id": 3, "doctor": "Dr. Meena", "date": "Sat", "time": "09:30 AM", "booked": False},
]
OTPS = {}        # mobile -> {"otp": "123456", "expires": time, "tries": 0}
VERIFIED = set() # mobiles that passed OTP

class ChatIn(BaseModel):
    message: str

class OtpIn(BaseModel):
    slot_id: int
    mobile: str

class VerifyIn(BaseModel):
    mobile: str
    otp: str

class BookIn(BaseModel):
    slot_id: int
    name: str
    mobile: str

@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/chat")
def chat(data: ChatIn):
    text = data.message.lower()
    # TODO (next step): replace with a Claude API call + tools
    if "clean" in text or "book" in text or "appointment" in text:
        free = [s for s in SLOTS if not s["booked"]]
        return {"reply": "Here are the available slots:", "ui": {"type": "slots", "slots": free}}
    return {"reply": "I can help you book. Try: cleaning on Saturday morning", "ui": None}

@app.post("/send-otp")
def send_otp(data: OtpIn):
    slot = next((s for s in SLOTS if s["id"] == data.slot_id), None)
    if not slot or slot["booked"]:
        return {"ok": False, "reply": "Sorry, that slot is no longer available."}
    if not (data.mobile.isdigit() and len(data.mobile) == 10):
        return {"ok": False, "reply": "Please enter a valid 10-digit mobile number."}
    otp = str(random.randint(100000, 999999))
    OTPS[data.mobile] = {"otp": otp, "expires": time.time() + 300, "tries": 0}
    # Real version: send `otp` by SMS here (Twilio / MSG91). Never return it to the browser.
    reply = f"OTP sent to {data.mobile}."
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

@app.post("/book")
def book(data: BookIn):
    if data.mobile not in VERIFIED:          # the rule: no OTP, no booking
        return {"ok": False, "reply": "Please verify your mobile number first."}
    for s in SLOTS:
        if s["id"] == data.slot_id:
            if s["booked"]:
                return {"ok": False, "reply": "Sorry, that slot was just taken."}
            s["booked"] = True
            VERIFIED.discard(data.mobile)
            return {"ok": True, "reply": f"Confirmed! {data.name}, {s['doctor']} on {s['date']} at {s['time']}."}
    return {"ok": False, "reply": "Slot not found."}
