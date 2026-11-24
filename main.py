# STEP 7: English / Hindi / Kannada, cancel + refund (test mode), dashboard statuses, on top of Steps 1-6.
# No AI key needed: requests are understood with rules (keywords in all three languages).
import os, random, re, time, uuid
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

app = FastAPI()
DEMO_MODE = True        # OTP shown on screen; payment and refund are simulated
DASHBOARD_KEY = os.environ.get("DASHBOARD_KEY", "demo123")
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
ORDERS = {}     # order_id -> {slot_id, name, mobile, service, status}   status: created/failed/paid/cancelled/completed/no_show

class ChatIn(BaseModel):
    message: str
    lang: str = "en"
class OtpIn(BaseModel):
    slot_id: int
    mobile: str
    lang: str = "en"
class VerifyIn(BaseModel):
    mobile: str
    otp: str
    lang: str = "en"
class OrderIn(BaseModel):
    slot_id: int
    name: str
    mobile: str
    service: str = "Dental visit"
    lang: str = "en"
class PayIn(BaseModel):
    order_id: str
    success: bool
    lang: str = "en"
class CancelIn(BaseModel):
    order_id: str
    mobile: str
    lang: str = "en"
class StatusIn(BaseModel):
    key: str
    order_id: str
    status: str

# ---------- translations (Hindi and Kannada: please have a native speaker check them) ----------
MSG = {
 "emergency": {
  "en": "This sounds urgent. Please call the clinic directly or go to the nearest hospital now. I can't treat emergencies in this chat.",
  "hi": "यह गंभीर लगता है। कृपया तुरंत क्लिनिक को फोन करें या नज़दीकी अस्पताल जाएँ। मैं इस चैट में आपातकालीन इलाज नहीं कर सकता।",
  "kn": "ಇದು ತುರ್ತು ಎನಿಸುತ್ತದೆ. ದಯವಿಟ್ಟು ತಕ್ಷಣ ಕ್ಲಿನಿಕ್‌ಗೆ ಕರೆ ಮಾಡಿ ಅಥವಾ ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಗೆ ಹೋಗಿ. ಈ ಚಾಟ್‌ನಲ್ಲಿ ತುರ್ತು ಚಿಕಿತ್ಸೆ ನೀಡಲು ಸಾಧ್ಯವಿಲ್ಲ."},
 "help": {
  "en": "I can book your dental visit. Try: cleaning with Dr. Rao on Saturday morning",
  "hi": "मैं आपकी दंत चिकित्सा की अपॉइंटमेंट बुक कर सकता हूँ। कोशिश करें: शनिवार सुबह डॉ. राव के साथ सफाई",
  "kn": "ನಾನು ನಿಮ್ಮ ದಂತ ಭೇಟಿಯನ್ನು ಬುಕ್ ಮಾಡಬಲ್ಲೆ. ಹೀಗೆ ಬರೆಯಿರಿ: ಶನಿವಾರ ಬೆಳಿಗ್ಗೆ ಡಾ. ರಾವ್ ಅವರೊಂದಿಗೆ ಕ್ಲೀನಿಂಗ್"},
 "no_slots": {
  "en": "Sorry, no slots are free right now. Please try again in a few minutes.",
  "hi": "क्षमा करें, अभी कोई स्लॉट खाली नहीं है। कृपया कुछ मिनट बाद फिर कोशिश करें।",
  "kn": "ಕ್ಷಮಿಸಿ, ಈಗ ಯಾವುದೇ ಸ್ಲಾಟ್ ಖಾಲಿ ಇಲ್ಲ. ದಯವಿಟ್ಟು ಕೆಲವು ನಿಮಿಷಗಳ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."},
 "slots_head": {
  "en": "{summary}: please choose a slot.",
  "hi": "{summary}: कृपया स्लॉट चुनें।",
  "kn": "{summary}: ದಯವಿಟ್ಟು ಸ್ಲಾಟ್ ಆಯ್ಕೆಮಾಡಿ."},
 "note_time": {
  "en": "No exact time match, but here are other times that day.",
  "hi": "सही समय नहीं मिला, पर उसी दिन के दूसरे समय ये हैं।",
  "kn": "ನಿಖರ ಸಮಯ ಸಿಗಲಿಲ್ಲ, ಆದರೆ ಅದೇ ದಿನದ ಇತರ ಸಮಯಗಳು ಇಲ್ಲಿವೆ."},
 "note_day": {
  "en": "No slots on that day, but here are this doctor's other days.",
  "hi": "उस दिन स्लॉट नहीं हैं, पर इन डॉक्टर के दूसरे दिन ये हैं।",
  "kn": "ಆ ದಿನ ಸ್ಲಾಟ್ ಇಲ್ಲ, ಆದರೆ ಈ ವೈದ್ಯರ ಇತರ ದಿನಗಳು ಇಲ್ಲಿವೆ."},
 "note_doctor": {
  "en": "That doctor isn't free then, but others are.",
  "hi": "उस समय वे डॉक्टर खाली नहीं हैं, पर दूसरे डॉक्टर उपलब्ध हैं।",
  "kn": "ಆ ಸಮಯದಲ್ಲಿ ಆ ವೈದ್ಯರು ಲಭ್ಯರಿಲ್ಲ, ಆದರೆ ಇತರರು ಇದ್ದಾರೆ."},
 "note_nearest": {
  "en": "I couldn't match everything, so here are the nearest options.",
  "hi": "सब कुछ मेल नहीं खा सका, इसलिए सबसे नज़दीकी विकल्प ये हैं।",
  "kn": "ಎಲ್ಲವೂ ಹೊಂದಲಿಲ್ಲ, ಆದ್ದರಿಂದ ಹತ್ತಿರದ ಆಯ್ಕೆಗಳು ಇಲ್ಲಿವೆ."},
 "slot_gone": {
  "en": "Sorry, that slot is no longer available.",
  "hi": "क्षमा करें, यह स्लॉट अब उपलब्ध नहीं है।",
  "kn": "ಕ್ಷಮಿಸಿ, ಆ ಸ್ಲಾಟ್ ಈಗ ಲಭ್ಯವಿಲ್ಲ."},
 "bad_mobile": {
  "en": "Please enter a valid 10-digit mobile number.",
  "hi": "कृपया 10 अंकों का सही मोबाइल नंबर दर्ज करें।",
  "kn": "ದಯವಿಟ್ಟು ಸರಿಯಾದ 10 ಅಂಕಿಯ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ನಮೂದಿಸಿ."},
 "otp_sent": {
  "en": "OTP sent to {mobile}. Slot held for 5 minutes.",
  "hi": "{mobile} पर OTP भेजा गया। स्लॉट 5 मिनट के लिए रोका गया है।",
  "kn": "{mobile} ಗೆ OTP ಕಳುಹಿಸಲಾಗಿದೆ. ಸ್ಲಾಟ್ 5 ನಿಮಿಷ ಕಾಯ್ದಿರಿಸಲಾಗಿದೆ."},
 "otp_demo": {
  "en": "(Demo mode: your OTP is {otp})",
  "hi": "(डेमो मोड: आपका OTP {otp} है)",
  "kn": "(ಡೆಮೊ ಮೋಡ್: ನಿಮ್ಮ OTP {otp})"},
 "otp_expired": {
  "en": "OTP expired. Please start again.",
  "hi": "OTP की समय सीमा समाप्त हो गई। कृपया फिर से शुरू करें।",
  "kn": "OTP ಅವಧಿ ಮುಗಿದಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ."},
 "otp_toomany": {
  "en": "Too many wrong attempts. Please start again.",
  "hi": "बहुत ज़्यादा गलत प्रयास। कृपया फिर से शुरू करें।",
  "kn": "ತುಂಬಾ ತಪ್ಪು ಪ್ರಯತ್ನಗಳು. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ."},
 "otp_wrong": {
  "en": "Wrong OTP. Try again.",
  "hi": "गलत OTP। फिर कोशिश करें।",
  "kn": "ತಪ್ಪಾದ OTP. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."},
 "otp_ok": {
  "en": "Mobile verified.",
  "hi": "मोबाइल सत्यापित हो गया।",
  "kn": "ಮೊಬೈಲ್ ಪರಿಶೀಲಿಸಲಾಗಿದೆ."},
 "verify_first": {
  "en": "Please verify your mobile number first.",
  "hi": "कृपया पहले अपना मोबाइल नंबर सत्यापित करें।",
  "kn": "ದಯವಿಟ್ಟು ಮೊದಲು ನಿಮ್ಮ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ಪರಿಶೀಲಿಸಿ."},
 "slot_taken": {
  "en": "Sorry, that slot was just taken.",
  "hi": "क्षमा करें, यह स्लॉट अभी-अभी बुक हो गया।",
  "kn": "ಕ್ಷಮಿಸಿ, ಆ ಸ್ಲಾಟ್ ಈಗಷ್ಟೇ ಬುಕ್ ಆಗಿದೆ."},
 "hold_expired": {
  "en": "Your 5-minute slot hold expired. Please start again.",
  "hi": "आपका 5 मिनट का स्लॉट होल्ड समाप्त हो गया। कृपया फिर से शुरू करें।",
  "kn": "ನಿಮ್ಮ 5 ನಿಮಿಷಗಳ ಸ್ಲಾಟ್ ಕಾಯ್ದಿರಿಕೆ ಮುಗಿದಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ."},
 "please_pay": {
  "en": "Please pay ₹{amount} to confirm your appointment.",
  "hi": "अपॉइंटमेंट की पुष्टि के लिए कृपया ₹{amount} का भुगतान करें।",
  "kn": "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ದೃಢೀಕರಿಸಲು ದಯವಿಟ್ಟು ₹{amount} ಪಾವತಿಸಿ."},
 "order_missing": {
  "en": "Order not found.",
  "hi": "ऑर्डर नहीं मिला।",
  "kn": "ಆರ್ಡರ್ ಸಿಗಲಿಲ್ಲ."},
 "pay_fail_retry": {
  "en": "Payment unsuccessful. Your slot is held for you for {left} more. Please try again.",
  "hi": "भुगतान असफल रहा। आपका स्लॉट आपके लिए {left} और रोका गया है। कृपया फिर कोशिश करें।",
  "kn": "ಪಾವತಿ ವಿಫಲವಾಗಿದೆ. ನಿಮ್ಮ ಸ್ಲಾಟ್ ಇನ್ನೂ {left} ಕಾಲ ಕಾಯ್ದಿರಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."},
 "pay_fail_expired": {
  "en": "Payment unsuccessful and your 5-minute slot hold has expired. Please start again.",
  "hi": "भुगतान असफल रहा और आपका 5 मिनट का स्लॉट होल्ड समाप्त हो गया। कृपया फिर से शुरू करें।",
  "kn": "ಪಾವತಿ ವಿಫಲವಾಗಿದೆ ಮತ್ತು ನಿಮ್ಮ 5 ನಿಮಿಷಗಳ ಕಾಯ್ದಿರಿಕೆ ಮುಗಿದಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ."},
 "pay_ok": {
  "en": "Payment successful. Your payment is verified and your slot is booked.",
  "hi": "भुगतान सफल रहा। आपका भुगतान सत्यापित हो गया है और आपका स्लॉट बुक हो गया है।",
  "kn": "ಪಾವತಿ ಯಶಸ್ವಿಯಾಗಿದೆ. ನಿಮ್ಮ ಪಾವತಿ ಪರಿಶೀಲಿಸಲಾಗಿದೆ ಮತ್ತು ನಿಮ್ಮ ಸ್ಲಾಟ್ ಬುಕ್ ಆಗಿದೆ."},
 "cancel_ok": {
  "en": "Appointment cancelled. A refund of ₹{amount} has been initiated (test mode).",
  "hi": "अपॉइंटमेंट रद्द हो गई। ₹{amount} की वापसी शुरू कर दी गई है (टेस्ट मोड)।",
  "kn": "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ರದ್ದಾಗಿದೆ. ₹{amount} ಮರುಪಾವತಿ ಆರಂಭಿಸಲಾಗಿದೆ (ಟೆಸ್ಟ್ ಮೋಡ್)."},
 "cancel_no": {
  "en": "This appointment can't be cancelled.",
  "hi": "यह अपॉइंटमेंट रद्द नहीं की जा सकती।",
  "kn": "ಈ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ರದ್ದುಮಾಡಲಾಗುವುದಿಲ್ಲ."},
}
DOC_NAMES = {"Dr. Rao": {"hi": "डॉ. राव", "kn": "ಡಾ. ರಾವ್"}, "Dr. Meena": {"hi": "डॉ. मीना", "kn": "ಡಾ. ಮೀನಾ"}}
SERVICE_NAMES = {
    "Cleaning": {"hi": "सफाई", "kn": "ಕ್ಲೀನಿಂಗ್"}, "Checkup": {"hi": "जांच", "kn": "ತಪಾಸಣೆ"},
    "Filling": {"hi": "फिलिंग", "kn": "ಫಿಲ್ಲಿಂಗ್"}, "Root canal": {"hi": "रूट कैनाल", "kn": "ರೂಟ್ ಕೆನಾಲ್"},
    "Extraction": {"hi": "दांत निकालना", "kn": "ಹಲ್ಲು ತೆಗೆಯುವಿಕೆ"},
    "Braces consultation": {"hi": "ब्रेसेस परामर्श", "kn": "ಬ್ರೇಸಸ್ ಸಮಾಲೋಚನೆ"},
    "Whitening": {"hi": "सफेदी", "kn": "ವೈಟ್ನಿಂಗ್"}, "Dental visit": {"hi": "दंत जांच", "kn": "ದಂತ ಭೇಟಿ"},
}
DAY_NAMES = {
    "hi": {"Mon": "सोमवार", "Tue": "मंगलवार", "Wed": "बुधवार", "Thu": "गुरुवार", "Fri": "शुक्रवार", "Sat": "शनिवार", "Sun": "रविवार"},
    "kn": {"Mon": "ಸೋಮವಾರ", "Tue": "ಮಂಗಳವಾರ", "Wed": "ಬುಧವಾರ", "Thu": "ಗುರುವಾರ", "Fri": "ಶುಕ್ರವಾರ", "Sat": "ಶನಿವಾರ", "Sun": "ಭಾನುವಾರ"},
}
PART_NAMES = {"hi": {"morning": "सुबह", "afternoon": "दोपहर", "evening": "शाम"},
              "kn": {"morning": "ಬೆಳಿಗ್ಗೆ", "afternoon": "ಮಧ್ಯಾಹ್ನ", "evening": "ಸಂಜೆ"}}

def tr(lang, key, **kw):
    table = MSG[key]
    return table.get(lang, table["en"]).format(**kw)

def detect_lang(text, default):
    if any("\u0c80" <= ch <= "\u0cff" for ch in text): return "kn"      # Kannada script
    if any("\u0900" <= ch <= "\u097f" for ch in text): return "hi"      # Devanagari (Hindi)
    return default if default in ("en", "hi", "kn") else "en"

def doc_name(d, lang): return DOC_NAMES.get(d, {}).get(lang, d)
def svc_name(s, lang): return SERVICE_NAMES.get(s, {}).get(lang, s)
def day_name(d, lang): return DAY_NAMES.get(lang, {}).get(d, d)
def part_name(p, lang): return PART_NAMES.get(lang, {}).get(p, p)

# ---------- helpers ----------
def get_slot(slot_id):
    return next((s for s in SLOTS if s["id"] == slot_id), None)

def held_by_other(slot_id, mobile=None):
    h = HOLDS.get(slot_id)
    if not h:
        return False
    if time.time() > h["expires"]:
        HOLDS.pop(slot_id, None)
        return False
    return mobile is None or h["mobile"] != mobile

def hold_left(slot_id):
    h = HOLDS.get(slot_id)
    return max(0, int(h["expires"] - time.time())) if h else 0

def holds_valid(slot_id, mobile):
    h = HOLDS.get(slot_id)
    return bool(h and h["mobile"] == mobile and time.time() <= h["expires"])

def slot_free(slot, mobile=None):
    return (not slot["booked"]) and (not held_by_other(slot["id"], mobile))

DAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
def appointment_start(slot):
    now = datetime.now()
    ahead = (DAYS[slot["date"]] - now.weekday()) % 7 or 7
    day = now + timedelta(days=ahead)
    t = datetime.strptime(slot["time"], "%I:%M %p")
    return day.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)

def fmt_date(when, lang):
    if lang == "en":
        return when.strftime("%a %d %b %Y")
    return when.strftime("%d-%m-%Y") + " (" + day_name(WEEKDAY_NAMES[when.weekday()], lang) + ")"

def booking_details(order_id, lang="en"):
    o = ORDERS[order_id]
    slot = get_slot(o["slot_id"])
    return {"name": o["name"], "mobile": o["mobile"], "service": svc_name(o["service"], lang),
            "doctor": doc_name(slot["doctor"], lang), "date": fmt_date(appointment_start(slot), lang),
            "time": slot["time"], "amount": AMOUNT, "receipt": order_id}

# ---------- understanding free text (English, Hindi, Kannada; no AI key needed) ----------
SERVICES = {
    "Cleaning": ["clean", "scaling", "polish", "सफाई", "सफ़ाई", "क्लीनिंग", "ಕ್ಲೀನಿಂಗ್", "ಸ್ವಚ್ಛ"],
    "Checkup": ["checkup", "check-up", "check up", "consult", "exam", "जांच", "जाँच", "चेकअप", "ತಪಾಸಣೆ", "ಚೆಕಪ್"],
    "Filling": ["filling", "cavity", "cavities", "फिलिंग", "ಫಿಲ್ಲಿಂಗ್"],
    "Root canal": ["root canal", "rct", "रूट कैनाल", "ರೂಟ್ ಕೆನಾಲ್"],
    "Extraction": ["extract", "tooth removal", "pull out", "दांत निकाल", "ಹಲ್ಲು ತೆಗೆ", "ಹಲ್ಲು ಕೀಳ"],
    "Braces consultation": ["brace", "aligner", "straighten", "ब्रेसेस", "ಬ್ರೇಸ್"],
    "Whitening": ["whiten", "सफेदी", "व्हाइटनिंग", "ವೈಟ್ನಿಂಗ್"],
}
EMERGENCY = ["severe pain", "bleeding", "swelling", "swollen", "emergency", "accident", "knocked out", "can't breathe", "unbearable",
             "तेज दर्द", "बहुत दर्द", "खून", "सूजन", "आपातकाल", "इमरजेंसी", "ತೀವ್ರ ನೋವು", "ತುಂಬಾ ನೋವು", "ರಕ್ತ", "ಊತ", "ತುರ್ತು"]
BOOKING_WORDS = ["book", "appointment", "slot", "schedule", "visit", "see ", "बुक", "अपॉइंटमेंट", "स्लॉट", "ಬುಕ್", "ಅಪಾಯಿಂಟ್", "ಸ್ಲಾಟ್"]
LOCAL_DOCS = {"राव": "Dr. Rao", "ರಾವ್": "Dr. Rao", "मीना": "Dr. Meena", "ಮೀನಾ": "Dr. Meena"}
LOCAL_DAYS = {"सोमवार": "Mon", "मंगलवार": "Tue", "बुधवार": "Wed", "गुरुवार": "Thu", "शुक्रवार": "Fri", "शनिवार": "Sat", "रविवार": "Sun",
              "ಸೋಮವಾರ": "Mon", "ಮಂಗಳವಾರ": "Tue", "ಬುಧವಾರ": "Wed", "ಗುರುವಾರ": "Thu", "ಶುಕ್ರವಾರ": "Fri", "ಶನಿವಾರ": "Sat", "ಭಾನುವಾರ": "Sun"}
LOCAL_PARTS = {"सुबह": "morning", "दोपहर": "afternoon", "शाम": "evening",
               "ಬೆಳಿಗ್ಗೆ": "morning", "ಮಧ್ಯಾಹ್ನ": "afternoon", "ಸಂಜೆ": "evening"}
DAY_WORDS = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}
FULL_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "tues", "thur", "thurs", "weds")

def find_service(text):
    for name, words in SERVICES.items():
        if any(w in text for w in words):
            return name
    return None

def find_doctor(text):
    for d in {s["doctor"] for s in SLOTS}:
        if d.lower().split()[-1] in text:
            return d
    for word, d in LOCAL_DOCS.items():
        if word in text:
            return d
    return None

def find_day(text):
    if "tomorrow" in text:
        return WEEKDAY_NAMES[(datetime.now().weekday() + 1) % 7]
    if "weekend" in text:
        return "Sat"
    for word, d in LOCAL_DAYS.items():
        if word in text:
            return d
    for word in re.findall(r"[a-z]+", text):
        if word[:3] in DAY_WORDS and (len(word) == 3 or word in FULL_DAYS):
            return DAY_WORDS[word[:3]]
    return None

def find_part_of_day(text):
    for part in ("morning", "afternoon", "evening"):
        if part in text:
            return part
    for word, part in LOCAL_PARTS.items():
        if word in text:
            return part
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if m:
        return "hour:%d" % (int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0))
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

@app.post("/chat")
def chat(data: ChatIn):
    text = data.message.lower()
    lang = detect_lang(data.message, data.lang)          # replies in the language the patient writes in
    if any(w in text for w in EMERGENCY):                # urgent symptoms: do not book, send to real help
        return {"reply": tr(lang, "emergency"), "ui": None, "lang": lang}
    want = understand(text)
    if not (want["service"] or want["doctor"] or want["day"] or want["part"] or any(w in text for w in BOOKING_WORDS)):
        return {"reply": tr(lang, "help"), "ui": None, "lang": lang}

    free = [s for s in SLOTS if slot_free(s)]
    service = want["service"] or "Dental visit"
    tries = [                                            # exact match first, then relax one condition at a time
        (want["doctor"], want["day"], want["part"], None),
        (want["doctor"], want["day"], None, "note_time"),
        (want["doctor"], None, None, "note_day"),
        (None, want["day"], want["part"], "note_doctor"),
        (None, None, None, "note_nearest"),
    ]
    found, note = [], None
    for doctor, day, part, note in tries:
        found = [s for s in free if matches(s, doctor, day, part)]
        if found:
            break
    if not found:
        return {"reply": tr(lang, "no_slots"), "ui": None, "lang": lang}
    summary = svc_name(service, lang)
    if want["doctor"]: summary += " · " + doc_name(want["doctor"], lang)
    if want["day"]: summary += " · " + day_name(want["day"], lang)
    if want["part"] and not want["part"].startswith("hour:"): summary += " · " + part_name(want["part"], lang)
    reply = (tr(lang, note) + " " if note else "") + tr(lang, "slots_head", summary=summary)
    return {"reply": reply, "lang": lang, "ui": {"type": "slots", "slots": found[:6], "service": service}}

@app.post("/send-otp")
def send_otp(data: OtpIn):
    lang = data.lang
    slot = get_slot(data.slot_id)
    if not slot or not slot_free(slot, data.mobile):
        return {"ok": False, "reply": tr(lang, "slot_gone")}
    if not (data.mobile.isdigit() and len(data.mobile) == 10):
        return {"ok": False, "reply": tr(lang, "bad_mobile")}
    otp = str(random.randint(100000, 999999))
    OTPS[data.mobile] = {"otp": otp, "expires": time.time() + 300, "tries": 0}
    HOLDS[slot["id"]] = {"mobile": data.mobile, "expires": time.time() + HOLD_SECONDS}
    reply = tr(lang, "otp_sent", mobile=data.mobile)
    if DEMO_MODE:                                        # real version: send the OTP by SMS here, never return it
        reply += " " + tr(lang, "otp_demo", otp=otp)
    return {"ok": True, "reply": reply}

@app.post("/verify-otp")
def verify_otp(data: VerifyIn):
    lang = data.lang
    rec = OTPS.get(data.mobile)
    if not rec or time.time() > rec["expires"]:
        return {"ok": False, "restart": True, "reply": tr(lang, "otp_expired")}
    rec["tries"] += 1
    if rec["tries"] > 3:
        OTPS.pop(data.mobile, None)
        return {"ok": False, "restart": True, "reply": tr(lang, "otp_toomany")}
    if data.otp != rec["otp"]:
        return {"ok": False, "reply": tr(lang, "otp_wrong")}
    VERIFIED.add(data.mobile)
    OTPS.pop(data.mobile, None)
    return {"ok": True, "reply": tr(lang, "otp_ok")}

@app.post("/create-order")
def create_order(data: OrderIn):
    lang = data.lang
    slot = get_slot(data.slot_id)
    if data.mobile not in VERIFIED:
        return {"ok": False, "reply": tr(lang, "verify_first")}
    if not slot or slot["booked"]:
        return {"ok": False, "reply": tr(lang, "slot_taken")}
    if not holds_valid(data.slot_id, data.mobile):
        return {"ok": False, "reply": tr(lang, "hold_expired")}
    order_id = "ord_" + uuid.uuid4().hex[:8]
    ORDERS[order_id] = {"slot_id": data.slot_id, "name": data.name, "mobile": data.mobile,
                        "service": data.service, "status": "created"}
    return {"ok": True, "order_id": order_id, "amount": AMOUNT, "hold_left": hold_left(data.slot_id),
            "reply": tr(lang, "please_pay", amount=AMOUNT)}

@app.post("/pay-demo")
def pay_demo(data: PayIn):
    # Real version: Razorpay calls a webhook on success; verify its signature, then run the booking code below.
    lang = data.lang
    order = ORDERS.get(data.order_id)
    if not order or order["status"] in ("cancelled", "completed", "no_show"):
        return {"ok": False, "reply": tr(lang, "order_missing")}
    slot = get_slot(order["slot_id"])
    if order["status"] == "paid":                        # idempotent: repeat calls never double-book
        return {"ok": True, "order_id": data.order_id, "reply": tr(lang, "pay_ok"),
                "details": booking_details(data.order_id, lang)}
    if not data.success:
        order["status"] = "failed"
        if holds_valid(order["slot_id"], order["mobile"]):   # the slot waits for this patient
            left = hold_left(order["slot_id"])
            return {"ok": False, "retry": True, "hold_left": left,
                    "reply": tr(lang, "pay_fail_retry", left=f"{left // 60}:{left % 60:02d}")}
        return {"ok": False, "reply": tr(lang, "pay_fail_expired")}
    if slot["booked"] or not holds_valid(order["slot_id"], order["mobile"]):
        return {"ok": False, "reply": tr(lang, "hold_expired")}
    slot["booked"] = True                                # booked ONLY after payment succeeds
    order["status"] = "paid"
    HOLDS.pop(order["slot_id"], None)
    VERIFIED.discard(order["mobile"])
    return {"ok": True, "order_id": data.order_id, "reply": tr(lang, "pay_ok"),
            "details": booking_details(data.order_id, lang)}

@app.post("/cancel")
def cancel(data: CancelIn):
    lang = data.lang
    order = ORDERS.get(data.order_id)
    if not order or order["mobile"] != data.mobile or order["status"] != "paid":
        return {"ok": False, "reply": tr(lang, "cancel_no")}
    order["status"] = "cancelled"
    get_slot(order["slot_id"])["booked"] = False         # the slot becomes available again
    return {"ok": True, "reply": tr(lang, "cancel_ok", amount=AMOUNT)}   # real version: call the gateway refund API

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

# ---------- doctor dashboard ----------
STATUS_LABEL = {"paid": "Confirmed", "completed": "Completed", "no_show": "No-show", "cancelled": "Cancelled"}

@app.get("/api/appointments")
def appointments(key: str = "", doctor: str = ""):
    if key != DASHBOARD_KEY:
        return {"ok": False, "reply": "Wrong or missing key."}
    rows = []
    counts = {"paid": 0, "completed": 0, "no_show": 0, "cancelled": 0}
    for order_id, o in ORDERS.items():
        if o["status"] not in STATUS_LABEL:
            continue
        slot = get_slot(o["slot_id"])
        if doctor and slot["doctor"] != doctor:
            continue
        counts[o["status"]] += 1
        when = appointment_start(slot)
        rows.append({"sort": when.isoformat(), "order_id": order_id, "patient": o["name"], "service": o["service"],
                     "doctor": slot["doctor"], "date": when.strftime("%a %d %b"), "time": slot["time"],
                     "mobile": "XXXXXX" + o["mobile"][-4:], "status": o["status"], "status_label": STATUS_LABEL[o["status"]]})
    rows.sort(key=lambda r: r["sort"])
    revenue = AMOUNT * (counts["paid"] + counts["completed"] + counts["no_show"])   # cancelled bookings are refunded
    return {"ok": True, "doctors": sorted({s["doctor"] for s in SLOTS}), "appointments": rows,
            "summary": {"confirmed": counts["paid"], "completed": counts["completed"], "no_show": counts["no_show"],
                        "cancelled": counts["cancelled"], "revenue": revenue}}

@app.post("/api/status")
def set_status(data: StatusIn):
    if data.key != DASHBOARD_KEY:
        return {"ok": False, "reply": "Wrong or missing key."}
    order = ORDERS.get(data.order_id)
    if not order or order["status"] != "paid" or data.status not in ("completed", "no_show"):
        return {"ok": False, "reply": "Only confirmed appointments can be marked Completed or No-show."}
    order["status"] = data.status
    return {"ok": True}
