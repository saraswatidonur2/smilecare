# STEP 9: all specialties, symptom triage, patient memory, preparation instructions, post-visit follow-up (on top of Steps 1-8).
# No AI key needed. English/Hindi/Kannada use hand-written text; other languages use the free deep-translator package.
import asyncio, html, io, os, random, re, time, uuid
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

try:
    from deep_translator import GoogleTranslator      # pip install deep-translator
except Exception:
    GoogleTranslator = None
try:
    import segno                                       # pip install segno  (QR codes)
except Exception:
    segno = None

app = FastAPI()
DEMO_MODE = True        # OTP shown on screen; payment and refund are simulated
DASHBOARD_KEY = os.environ.get("DASHBOARD_KEY", "demo123")
HOLD_SECONDS = 300      # a slot is held for 5 minutes while the patient pays
AMOUNT = 500            # consultation fee in rupees
CLINIC_NAME = "SmileCare Clinic"      # shown on the calendar invite and the check-in page
FOLLOWUP_DELAY = timedelta(hours=24)   # follow-up message goes out this long after the visit is marked Completed

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
    {"id": 10, "doctor": "Dr. Iyer",     "date": "Mon", "time": "09:00 AM", "booked": False},
    {"id": 11, "doctor": "Dr. Iyer",     "date": "Tue", "time": "06:00 PM", "booked": False},
    {"id": 12, "doctor": "Dr. Iyer",     "date": "Sat", "time": "09:00 AM", "booked": False},
    {"id": 13, "doctor": "Dr. Shah",     "date": "Wed", "time": "10:30 AM", "booked": False},
    {"id": 14, "doctor": "Dr. Shah",     "date": "Sat", "time": "11:30 AM", "booked": False},
    {"id": 15, "doctor": "Dr. Nair",     "date": "Tue", "time": "11:00 AM", "booked": False},
    {"id": 16, "doctor": "Dr. Nair",     "date": "Thu", "time": "05:00 PM", "booked": False},
    {"id": 17, "doctor": "Dr. Nair",     "date": "Sat", "time": "10:00 AM", "booked": False},
    {"id": 18, "doctor": "Dr. Kulkarni", "date": "Mon", "time": "04:00 PM", "booked": False},
    {"id": 19, "doctor": "Dr. Kulkarni", "date": "Fri", "time": "10:00 AM", "booked": False},
    {"id": 20, "doctor": "Dr. Kulkarni", "date": "Sat", "time": "12:00 PM", "booked": False},
]
# One line per doctor. To support another kind of treatment, add the doctor here, add slots above, and add the specialty below.
DOCTOR_SPECIALTY = {"Dr. Rao": "Dental", "Dr. Meena": "Dental", "Dr. Iyer": "General Medicine",
                    "Dr. Shah": "Dermatology", "Dr. Nair": "Cardiology", "Dr. Kulkarni": "Orthopedics"}
for _s in SLOTS:
    _s["specialty"] = DOCTOR_SPECIALTY[_s["doctor"]]
PATIENTS = {}   # mobile -> {name, visits, last_service}: saved after the first paid booking, so we never ask twice
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
class TranslateIn(BaseModel):
    lang: str
    texts: list
class ReschedOptIn(BaseModel):
    order_id: str
    mobile: str
    lang: str = "en"
class ReschedIn(BaseModel):
    order_id: str
    mobile: str
    slot_id: int
    lang: str = "en"
class RecoverIn(BaseModel):
    slot_id: int
    service: str = "Dental visit"
    lang: str = "en"
class FollowupIn(BaseModel):
    order_id: str
    answer: str          # better / same / worse
    lang: str = "en"
class KeyIn(BaseModel):
    key: str
class StatusIn(BaseModel):
    key: str
    order_id: str
    status: str

# ---------- translations (Hindi and Kannada: please have a native speaker check them) ----------
MSG = {
 "emergency": {
  "en": "This sounds urgent. Please call the clinic directly or go to the nearest hospital now. I can't treat emergencies in this chat. In India, dial 112.",
  "hi": "यह गंभीर लगता है। कृपया तुरंत क्लिनिक को फोन करें या नज़दीकी अस्पताल जाएँ। मैं इस चैट में आपातकालीन इलाज नहीं कर सकता। भारत में 112 पर कॉल करें।",
  "kn": "ಇದು ತುರ್ತು ಎನಿಸುತ್ತದೆ. ದಯವಿಟ್ಟು ತಕ್ಷಣ ಕ್ಲಿನಿಕ್‌ಗೆ ಕರೆ ಮಾಡಿ ಅಥವಾ ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಗೆ ಹೋಗಿ. ಈ ಚಾಟ್‌ನಲ್ಲಿ ತುರ್ತು ಚಿಕಿತ್ಸೆ ನೀಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ಭಾರತದಲ್ಲಿ 112 ಗೆ ಕರೆ ಮಾಡಿ."},
 "help": {
  "en": "I can book a doctor visit for any kind of treatment. Tell me your symptoms or what you need, for example: fever and cough, any evening, or cleaning with Dr. Rao on Saturday morning",
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
 "resched_pick": {
  "en": "Choose a new time:",
  "hi": "नया समय चुनें:",
  "kn": "ಹೊಸ ಸಮಯ ಆಯ್ಕೆಮಾಡಿ:"},
 "resched_none": {
  "en": "No other slots are free right now.",
  "hi": "अभी कोई और स्लॉट खाली नहीं है।",
  "kn": "ಈಗ ಬೇರೆ ಸ್ಲಾಟ್ ಖಾಲಿ ಇಲ್ಲ."},
 "resched_ok": {
  "en": "Appointment rescheduled. Your payment carries over, so no new payment is needed.",
  "hi": "अपॉइंटमेंट का समय बदल दिया गया। आपका भुगतान आगे जोड़ दिया गया है, नया भुगतान नहीं चाहिए।",
  "kn": "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಸಮಯ ಬದಲಾಗಿದೆ. ನಿಮ್ಮ ಪಾವತಿ ಮುಂದುವರಿಯುತ್ತದೆ, ಹೊಸ ಪಾವತಿ ಬೇಕಿಲ್ಲ."},
 "resched_no": {
  "en": "This appointment can't be rescheduled.",
  "hi": "यह अपॉइंटमेंट बदली नहीं जा सकती।",
  "kn": "ಈ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬದಲಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ."},
 "recover_head": {
  "en": "Your slot hold ended and the slot was released for other patients. Here are the nearest alternatives:",
  "hi": "आपका स्लॉट होल्ड समाप्त हो गया और स्लॉट दूसरे मरीज़ों के लिए खोल दिया गया। सबसे नज़दीकी विकल्प ये हैं:",
  "kn": "ನಿಮ್ಮ ಸ್ಲಾಟ್ ಕಾಯ್ದಿರಿಕೆ ಮುಗಿದು ಸ್ಲಾಟ್ ಇತರ ರೋಗಿಗಳಿಗೆ ಬಿಡುಗಡೆಯಾಗಿದೆ. ಹತ್ತಿರದ ಆಯ್ಕೆಗಳು ಇಲ್ಲಿವೆ:"},
 "triage_note": {
  "en": "I can't diagnose, but what you describe fits {specialty}. Here are the available doctors. The doctor will assess you properly at the visit."},
 "ask_need": {
  "en": "Tell me what is troubling you, or which kind of doctor you need ({specialties}), and your preferred day. I will show real slots."},
 "welcome_back": {
  "en": "Welcome back, {name}. I already have your details, so you do not need to enter them again."},
 "fu_better": {
  "en": "Glad you are feeling better! If anything changes, you can book again anytime."},
 "fu_same": {
  "en": "Sorry you are not better yet. A follow-up visit is a good idea, and you can book one now."},
 "fu_worse": {
  "en": "I am sorry you are feeling worse. Please call the clinic today, or go to the nearest hospital if it is severe. You can also book a follow-up now."},
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

CURATED = ("en", "hi", "kn")           # hand-written; other languages go through the translation package
FULL_DAY = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
_cache = {}

def translate_text(text, target, source="en"):
    """Translate with the free deep-translator package. If the service is unavailable, the English text is returned."""
    if not text or target == source:
        return text
    key = (text, target, source)
    if key in _cache:
        return _cache[key]
    if GoogleTranslator is None:
        return text
    try:
        out = GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        return text
    if not out:
        return text
    _cache[key] = out
    return out

def translate_template(template, target, kw=None):
    """Translate a message with {placeholders}. Values (OTP, mobile, amount...) are protected and never translated."""
    names = list(dict.fromkeys(re.findall(r"\{(\w+)\}", template)))
    tokens = {n: f"QQ{i}QQ" for i, n in enumerate(names)}
    protected = template
    for n, tok in tokens.items():
        protected = protected.replace("{" + n + "}", tok)
    out = translate_text(protected, target)
    if any(tok not in out for tok in tokens.values()):          # translator damaged a placeholder: stay in English
        return template.format(**kw) if kw is not None else template
    for n, tok in tokens.items():
        out = out.replace(tok, str(kw[n]) if kw is not None else "{" + n + "}")
    return out

def tr(lang, key, **kw):
    table = MSG[key]
    if lang in table:
        return table[lang].format(**kw)
    return translate_template(table["en"], lang, kw)

# script -> language (the dropdown choice wins when it uses the same script, e.g. Marathi or Nepali in Devanagari)
SCRIPT_RANGES = [("kn", 0x0C80, 0x0CFF), ("te", 0x0C00, 0x0C7F), ("ta", 0x0B80, 0x0BFF), ("ml", 0x0D00, 0x0D7F),
                 ("or", 0x0B00, 0x0B7F), ("gu", 0x0A80, 0x0AFF), ("pa", 0x0A00, 0x0A7F), ("bn", 0x0980, 0x09FF),
                 ("hi", 0x0900, 0x097F), ("ur", 0x0600, 0x06FF), ("sat", 0x1C50, 0x1C7F), ("mni-mtei", 0xABC0, 0xABFF)]
SAME_SCRIPT = {"hi": {"hi", "mr", "ne", "mai", "sa", "gom", "doi", "brx"}, "bn": {"bn", "as"}, "ur": {"ur", "sd", "ks"}}

def detect_lang(text, default):
    for ch in text:
        o = ord(ch)
        for code, lo, hi in SCRIPT_RANGES:
            if lo <= o <= hi:
                return default if default in SAME_SCRIPT.get(code, {code}) else code
    return default or "en"

def doc_name(d, lang): return DOC_NAMES.get(d, {}).get(lang, d)
def svc_name(s, lang):
    if lang in CURATED: return SERVICE_NAMES.get(s, {}).get(lang, s)
    return translate_text(s, lang)
def day_name(d, lang):
    if lang in DAY_NAMES: return DAY_NAMES[lang].get(d, d)
    if lang == "en": return d
    return translate_text(FULL_DAY.get(d, d), lang)
def part_name(p, lang):
    if lang in PART_NAMES: return PART_NAMES[lang].get(p, p)
    return p if lang == "en" else translate_text(p, lang)

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

def order_start(o):
    """The appointment time fixed when the booking was paid (or rescheduled)."""
    return o.get("start") or appointment_start(get_slot(o["slot_id"]))

def fmt_date(when, lang):
    if lang == "en":
        return when.strftime("%a %d %b %Y")
    return when.strftime("%d-%m-%Y") + " (" + day_name(WEEKDAY_NAMES[when.weekday()], lang) + ")"

def booking_details(order_id, lang="en"):
    o = ORDERS[order_id]
    slot = get_slot(o["slot_id"])
    return {"name": o["name"], "mobile": o["mobile"], "service": svc_name(o["service"], lang),
            "doctor": doc_name(slot["doctor"], lang), "date": fmt_date(order_start(o), lang),
            "time": slot["time"], "amount": AMOUNT, "receipt": order_id, "prep": prep_text(o, lang)}

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
EMERGENCY = ["severe pain", "bleeding", "swelling", "swollen", "emergency", "accident", "knocked out", "can't breathe", "unbearable", "chest pain", "difficulty breathing", "shortness of breath",
             "unconscious", "seizure", "fainted", "overdose",
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

# ---------- specialties: words that point to each one, and what to tell the patient before the visit ----------
SPECIALTIES = {
    "Dental": {
        "words": ["tooth", "teeth", "gum", "dental", "dentist", "cavity", "cavities", "jaw", "wisdom", "braces", "root canal",
                  "cleaning", "scaling", "whiten"],
        "prep": "Brush and floss before you come, bring any earlier dental X-rays, and tell the dentist about your medicines and allergies."},
    "General Medicine": {
        "words": ["fever", "cold", "cough", "flu", "headache", "migraine", "body ache", "fatigue", "tired", "weakness", "stomach",
                  "vomit", "nausea", "diarrhea", "diarrhoea", "sore throat", "infection", "diabetes", "sugar", "thyroid", "physician"],
        "prep": "Note down when your symptoms started and what makes them better or worse. Bring earlier prescriptions or reports and a list of your medicines. If the clinic mentions a blood test, ask whether you need to fast."},
    "Dermatology": {
        "words": ["skin", "rash", "itch", "acne", "pimple", "hair fall", "hair loss", "dandruff", "eczema", "fungal", "wart", "dermat"],
        "prep": "Do not put creams or makeup on the affected area before the visit. Bring the products you currently use, and a photo of how it looked earlier if it has changed."},
    "Cardiology": {
        "words": ["heart", "palpitation", "blood pressure", "hypertension", "cholesterol", "cardio", "ecg"],
        "prep": "Bring earlier ECG or other heart reports and a list of all your medicines. Wear comfortable clothes. Ask the clinic if any test needs fasting."},
    "Orthopedics": {
        "words": ["bone", "joint", "knee", "back pain", "neck pain", "shoulder", "fracture", "sprain", "ortho", "arthritis", "spine", "ankle", "muscle"],
        "prep": "Wear loose clothing so the doctor can see the area. Bring any X-rays, MRI films or reports. Avoid heavy strain on the painful area that day."},
}

def find_specialty(text):
    """The specialty whose words appear most often in the patient's message (None if no symptom words)."""
    best, top = None, 0
    for name, info in SPECIALTIES.items():
        score = sum(1 for w in info["words"] if w in text)
        if score > top:
            best, top = name, score
    return best

def prep_text(o, lang="en"):
    info = SPECIALTIES.get(get_slot(o["slot_id"])["specialty"], {})
    text = ("Before your visit: " + info.get("prep", "Bring any earlier reports and a list of your medicines.")
            + " Please arrive 10 minutes early and bring a photo ID.")
    return text if lang == "en" else translate_text(text, lang)

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

CENTER_HOUR = {"morning": 9, "afternoon": 14, "evening": 18}
def slot_hour(slot):
    return datetime.strptime(slot["time"], "%I:%M %p").hour

def closeness(slot, want):
    """How near a slot is to what the patient asked for (smaller is nearer)."""
    day_gap = abs(DAYS[slot["date"]] - DAYS[want["day"]]) if want["day"] else 0
    p = want["part"]
    target = int(p.split(":")[1]) if p and p.startswith("hour:") else (CENTER_HOUR.get(p) if p else None)
    return (day_gap, abs(slot_hour(slot) - target) if target is not None else 0)

@app.post("/chat")
def chat(data: ChatIn):
    text = data.message.lower()
    lang = detect_lang(data.message, data.lang)          # replies in the language the patient writes in
    want = understand(text)
    english = ""
    if not text.isascii() and not (want["service"] or want["doctor"] or want["day"] or want["part"]):
        english = translate_text(data.message, "en", source="auto").lower()   # any other Indian language
        want = understand(english)
    full = text + " " + english
    if any(w in full for w in EMERGENCY):                # urgent symptoms: do not book, send to real help
        return {"reply": tr(lang, "emergency"), "ui": None, "lang": lang}
    symptom_spec = find_specialty(full)
    if want["doctor"]:
        spec = DOCTOR_SPECIALTY[want["doctor"]]
    else:
        spec = symptom_spec or ("Dental" if want["service"] else None)
    all_specs = sorted({s["specialty"] for s in SLOTS})
    if spec is None and len(all_specs) == 1:                # a single-specialty clinic needs no question
        spec = all_specs[0]
    if not (want["service"] or want["doctor"] or want["day"] or want["part"] or spec or any(w in full for w in BOOKING_WORDS)):
        return {"reply": tr(lang, "help"), "ui": None, "lang": lang}
    if spec is None:                                        # wants to book, but we cannot tell with whom
        return {"reply": tr(lang, "ask_need", specialties=", ".join(all_specs)), "ui": None, "lang": lang}

    free = [s for s in SLOTS if slot_free(s) and s["specialty"] == spec]
    service = (want["service"] or "Dental visit") if spec == "Dental" else spec + " consultation"
    triage = bool(symptom_spec) and not want["doctor"] and not want["service"] and symptom_spec == spec
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
    if note:                                             # no exact match: the 3 closest alternatives
        found = sorted(found, key=lambda s: closeness(s, want))[:3]
    summary = svc_name(service, lang)
    if want["doctor"]: summary += " · " + doc_name(want["doctor"], lang)
    if want["day"]: summary += " · " + day_name(want["day"], lang)
    if want["part"] and not want["part"].startswith("hour:"): summary += " · " + part_name(want["part"], lang)
    reply = (tr(lang, "triage_note", specialty=spec) + " " if triage else "") \
            + (tr(lang, note) + " " if note else "") + tr(lang, "slots_head", summary=summary)
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
    known = PATIENTS.get(data.mobile)                     # returning patient: the page can pre-fill the name
    reply = tr(lang, "otp_ok") + ((" " + tr(lang, "welcome_back", name=known["name"])) if known else "")
    return {"ok": True, "reply": reply, "patient": known}

@app.post("/create-order")
def create_order(data: OrderIn):
    lang = data.lang
    slot = get_slot(data.slot_id)
    if data.mobile not in VERIFIED:
        return {"ok": False, "reply": tr(lang, "verify_first")}
    if not slot or slot["booked"]:
        return {"ok": False, "reply": tr(lang, "slot_taken")}
    if not holds_valid(data.slot_id, data.mobile):
        return {"ok": False, "expired": True, "reply": tr(lang, "hold_expired")}
    order_id = "ord_" + uuid.uuid4().hex[:8]
    ORDERS[order_id] = {"slot_id": data.slot_id, "name": data.name, "mobile": data.mobile,
                        "service": data.service, "status": "created"}
    return {"ok": True, "order_id": order_id, "amount": AMOUNT, "hold_left": hold_left(data.slot_id), "slot_id": data.slot_id, "service": data.service,
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
        return {"ok": False, "expired": True, "reply": tr(lang, "pay_fail_expired")}
    if slot["booked"] or not holds_valid(order["slot_id"], order["mobile"]):
        return {"ok": False, "expired": True, "reply": tr(lang, "hold_expired")}
    slot["booked"] = True                                # booked ONLY after payment succeeds
    order["status"] = "paid"
    order["start"] = appointment_start(slot)
    HOLDS.pop(order["slot_id"], None)
    VERIFIED.discard(order["mobile"])
    prev = PATIENTS.get(order["mobile"], {})
    PATIENTS[order["mobile"]] = {"name": order["name"], "visits": prev.get("visits", 0) + 1, "last_service": order["service"]}
    send_reminder(data.order_id, "Preparation instructions", prep_text(order, "en"))      # simulated, like the other reminders
    return {"ok": True, "order_id": data.order_id, "reply": tr(lang, "pay_ok") + " " + prep_text(order, lang),
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
    start = order_start(order)
    end = start + timedelta(minutes=30)
    f = "%Y%m%dT%H%M%S"
    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SmileCare//EN", "BEGIN:VEVENT",
        f"UID:{order_id}@smilecare", f"DTSTAMP:{datetime.utcnow().strftime(f)}Z",
        f"DTSTART:{start.strftime(f)}", f"DTEND:{end.strftime(f)}",
        f"SUMMARY:{order['service']} with {slot['doctor']}", f"LOCATION:{CLINIC_NAME}",
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
        when = order_start(o)
        rows.append({"sort": when.isoformat(), "order_id": order_id, "patient": o["name"], "service": o["service"],
                     "doctor": slot["doctor"], "date": when.strftime("%a %d %b"), "time": slot["time"],
                     "mobile": "XXXXXX" + o["mobile"][-4:], "status": o["status"], "status_label": STATUS_LABEL[o["status"]],
                     "followup": o.get("followup_answer", "")})
    rows.sort(key=lambda r: r["sort"])
    revenue = AMOUNT * (counts["paid"] + counts["completed"] + counts["no_show"])   # cancelled bookings are refunded
    return {"ok": True, "doctors": sorted({s["doctor"] for s in SLOTS}), "appointments": rows, "reminders": REMINDER_LOG[-15:][::-1],
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
    if data.status == "completed":
        order["completed_at"] = datetime.now()               # the follow-up message is planned from this moment
    return {"ok": True}


# ---------- all Indian languages ----------
INDIAN_LANGS = [("en", "English"), ("hi", "हिन्दी"), ("kn", "ಕನ್ನಡ"), ("bn", "বাংলা"), ("te", "తెలుగు"), ("mr", "मराठी"),
                ("ta", "தமிழ்"), ("ur", "اردو"), ("gu", "ગુજરાતી"), ("ml", "മലയാളം"), ("or", "ଓଡ଼ିଆ"), ("pa", "ਪੰਜਾਬੀ"),
                ("as", "অসমীয়া"), ("mai", "मैथिली"), ("sa", "संस्कृतम्"), ("ne", "नेपाली"), ("sd", "سنڌي"),
                ("gom", "कोंकणी"), ("doi", "डोगरी"), ("mni-mtei", "মৈতৈলোন্"), ("ks", "کٲشُر"), ("brx", "बड़ो"), ("sat", "ᱥᱟᱱᱛᱟᱲᱤ")]
_supported = None

def supported_codes():
    """Languages the translation package supports (asked once, when the internet is reachable)."""
    global _supported
    if _supported is None:
        codes = set(CURATED)
        if GoogleTranslator is not None:
            try:
                got = GoogleTranslator(source="en", target="hi").get_supported_languages(as_dict=True)
                _supported = codes | {c.lower() for c in got.values()}
                return _supported
            except Exception:
                return codes
        return codes
    return _supported

@app.get("/api/languages")
def languages():
    ok = supported_codes()
    return {"languages": [{"code": c, "name": n} for c, n in INDIAN_LANGS if c in ok or c in CURATED]}

@app.post("/api/translate")
def translate_api(data: TranslateIn):
    if data.lang not in {c for c, _ in INDIAN_LANGS} or len(data.texts) > 60:
        return {"ok": False, "texts": data.texts}
    return {"ok": True, "texts": [translate_template(str(t)[:300], data.lang) for t in data.texts]}

# ---------- reschedule (payment carries over) ----------
def free_slots_for(order, mobile):
    doc = get_slot(order["slot_id"])["doctor"]
    free = [s for s in SLOTS if s["id"] != order["slot_id"] and slot_free(s, mobile)
            and s["specialty"] == get_slot(order["slot_id"])["specialty"]]
    free.sort(key=lambda s: (s["doctor"] != doc, DAYS[s["date"]], slot_hour(s)))
    return free

@app.post("/reschedule-options")
def reschedule_options(data: ReschedOptIn):
    lang = data.lang
    order = ORDERS.get(data.order_id)
    if not order or order["mobile"] != data.mobile or order["status"] != "paid":
        return {"ok": False, "reply": tr(lang, "resched_no")}
    free = free_slots_for(order, data.mobile)[:6]
    if not free:
        return {"ok": False, "reply": tr(lang, "resched_none")}
    return {"ok": True, "reply": tr(lang, "resched_pick"), "slots": free}

@app.post("/reschedule")
def reschedule(data: ReschedIn):
    lang = data.lang
    order = ORDERS.get(data.order_id)
    new = get_slot(data.slot_id)
    if not order or order["mobile"] != data.mobile or order["status"] != "paid" or order.get("reschedules", 0) >= 2:
        return {"ok": False, "reply": tr(lang, "resched_no")}
    if not new or not slot_free(new, data.mobile):
        return {"ok": False, "reply": tr(lang, "slot_gone")}
    get_slot(order["slot_id"])["booked"] = False          # the old slot opens up for others
    new["booked"] = True
    order["slot_id"] = new["id"]
    order["start"] = appointment_start(new)
    order["reschedules"] = order.get("reschedules", 0) + 1
    order["reminded"] = []                                # reminders are planned again for the new time
    return {"ok": True, "reply": tr(lang, "resched_ok"), "details": booking_details(data.order_id, lang)}

# ---------- smart slot recovery ----------
@app.post("/recover")
def recover(data: RecoverIn):
    """After a hold ends without payment the slot is open again; offer the 3 nearest alternatives."""
    lang = data.lang
    gone = get_slot(data.slot_id)
    free = [s for s in SLOTS if s["id"] != data.slot_id and slot_free(s) and (not gone or s["specialty"] == gone["specialty"])]
    if gone:
        free.sort(key=lambda s: (s["doctor"] != gone["doctor"], abs(DAYS[s["date"]] - DAYS[gone["date"]]), abs(slot_hour(s) - slot_hour(gone))))
    if not free:
        return {"ok": False, "reply": tr(lang, "no_slots")}
    return {"ok": True, "reply": tr(lang, "recover_head"), "slots": free[:3], "service": data.service}

# ---------- QR check-in pass ----------
@app.get("/qr/{order_id}.svg")
def qr_code(order_id: str, base: str = ""):
    order = ORDERS.get(order_id)
    if not order or order["status"] != "paid" or segno is None:
        return Response("Not available", status_code=404)
    url = (base if base.startswith("http") else "") + "/checkin/" + order_id
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=5, border=2)
    return Response(buf.getvalue(), media_type="image/svg+xml")

@app.get("/checkin/{order_id}")
def checkin(order_id: str):
    """Opened when the QR code is scanned at reception. Shows only what the front desk needs (first name, no mobile)."""
    o = ORDERS.get(order_id)
    if not o or o["status"] not in ("paid", "completed"):
        return HTMLResponse("<h3>Booking not found</h3>", status_code=404)
    slot = get_slot(o["slot_id"])
    when = order_start(o)
    first = html.escape((o["name"].split() or [""])[0])
    status = "Confirmed and paid" if o["status"] == "paid" else "Completed"
    page = ("<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
            "<body style='font-family:sans-serif;max-width:420px;margin:30px auto'>"
            f"<h2>{html.escape(CLINIC_NAME)} check-in</h2>"
            f"<p><b>Booking ID:</b> {html.escape(order_id)}</p><p><b>Patient:</b> {first}</p>"
            f"<p><b>Service:</b> {html.escape(o['service'])}</p><p><b>Doctor:</b> {html.escape(slot['doctor'])}</p>"
            f"<p><b>When:</b> {when.strftime('%a %d %b %Y')}, {slot['time']}</p>"
            f"<p style='color:#15803d'><b>Status: {status}</b></p></body></html>")
    return HTMLResponse(page)

# ---------- automatic reminders (simulated: logged, not sent) ----------
REMINDER_LOG = []
REMINDER_OFFSETS = [("24 hours before", timedelta(hours=24)), ("2 hours before", timedelta(hours=2))]

def send_reminder(order_id, kind, text=""):
    """Real version: send a WhatsApp or SMS message here. In this prototype the reminder is only logged."""
    o = ORDERS[order_id]
    REMINDER_LOG.append({"time": datetime.now().strftime("%H:%M:%S"), "order_id": order_id, "patient": o["name"],
                         "kind": kind, "text": text, "channel": "WhatsApp/SMS (simulated)"})

def run_reminders(force=False):
    now, sent = datetime.now(), 0
    for order_id, o in ORDERS.items():
        if o["status"] != "paid":
            continue
        done = o.setdefault("reminded", [])
        for kind, delta in REMINDER_OFFSETS:
            if kind not in done and (force or now >= order_start(o) - delta):
                send_reminder(order_id, kind)
                done.append(kind)
                sent += 1
    for order_id, o in ORDERS.items():                         # post-visit follow-up for completed visits
        if o["status"] == "completed" and not o.get("followup_sent") and (force or now >= o.get("completed_at", now) + FOLLOWUP_DELAY):
            first = (o["name"].split() or [""])[0]
            send_reminder(order_id, "Post-visit follow-up",
                          f"Hi {first}, how are you feeling after your visit? Tap to tell us: /followup/{order_id}")
            o["followup_sent"] = True
            sent += 1
    return sent

@app.post("/api/reminders/run")
def reminders_run(data: KeyIn):
    if data.key != DASHBOARD_KEY:
        return {"ok": False, "reply": "Wrong or missing key."}
    return {"ok": True, "sent": run_reminders(force=True)}      # demo button: send the reminders right now

async def _reminder_loop():
    while True:
        try:
            run_reminders()
        except Exception:
            pass
        await asyncio.sleep(30)

@app.on_event("startup")
async def _start_reminders():
    asyncio.create_task(_reminder_loop())


# ---------- post-visit follow-up (the link inside the follow-up message opens this page) ----------
@app.get("/followup/{order_id}")
def followup_page(order_id: str, lang: str = "en"):
    o = ORDERS.get(order_id)
    if not o or o["status"] != "completed":
        return HTMLResponse("<h3>Link not available</h3>", status_code=404)
    lang = re.sub(r"[^a-z-]", "", lang.lower())[:10] or "en"
    first = html.escape((o["name"].split() or [""])[0])
    page = ("<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
            "<body style='font-family:sans-serif;max-width:420px;margin:30px auto;padding:0 12px'>"
            f"<h2>{html.escape(CLINIC_NAME)}</h2><p>Hi {first}, how are you feeling after your visit?</p>"
            "<button style='padding:12px;margin:4px' onclick=\"send('better')\">Better</button>"
            "<button style='padding:12px;margin:4px' onclick=\"send('same')\">Same</button>"
            "<button style='padding:12px;margin:4px' onclick=\"send('worse')\">Worse</button>"
            "<p id='out' style='margin-top:16px'></p>"
            "<p id='book' style='display:none'><a href='/'>Book a follow-up visit</a></p>"
            "<script>function send(a){fetch('/followup-reply',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({order_id:'__ID__',answer:a,lang:'__LANG__'})}).then(function(r){return r.json()}).then(function(d){"
            "document.getElementById('out').textContent=d.reply;"
            "if(d.rebook){document.getElementById('book').style.display='block';}});}</script></body></html>")
    return HTMLResponse(page.replace("__ID__", html.escape(order_id)).replace("__LANG__", lang))

@app.post("/followup-reply")
def followup_reply(data: FollowupIn):
    lang = data.lang
    o = ORDERS.get(data.order_id)
    if not o or o["status"] != "completed" or data.answer not in ("better", "same", "worse"):
        return {"ok": False, "reply": tr(lang, "cancel_no")}
    o["followup_answer"] = data.answer                       # the doctor sees this on the dashboard
    return {"ok": True, "rebook": data.answer != "better", "reply": tr(lang, "fu_" + data.answer)}
