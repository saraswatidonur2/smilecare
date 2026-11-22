# BACKEND: FastAPI. Holds the data and rules. The frontend only talks to it through URLs.
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

# Fake "clinic system" (later: SQLite database)
SLOTS = [
    {"id": 1, "doctor": "Dr. Rao",   "date": "Sat", "time": "10:00 AM", "booked": False},
    {"id": 2, "doctor": "Dr. Rao",   "date": "Sat", "time": "11:00 AM", "booked": False},
    {"id": 3, "doctor": "Dr. Meena", "date": "Sat", "time": "09:30 AM", "booked": False},
]

class ChatIn(BaseModel):
    message: str

class BookIn(BaseModel):
    slot_id: int
    name: str

@app.get("/")                      # serves the frontend page
def home():
    return FileResponse("index.html")

@app.post("/chat")                 # frontend sends the patient's message here
def chat(data: ChatIn):
    text = data.message.lower()
    # TODO: replace this keyword check with a Claude API call + tools
    if "clean" in text or "book" in text or "appointment" in text:
        free = [s for s in SLOTS if not s["booked"]]
        return {"reply": "Here are the available slots:", "ui": {"type": "slots", "slots": free}}
    return {"reply": "I can help you book. Try: cleaning on Saturday morning", "ui": None}

@app.post("/book")                 # frontend sends the chosen slot and name here
def book(data: BookIn):
    for s in SLOTS:
        if s["id"] == data.slot_id:
            if s["booked"]:        # rule lives in the backend, not the frontend
                return {"ok": False, "reply": "Sorry, that slot was just taken."}
            s["booked"] = True
            return {"ok": True, "reply": f"Confirmed! {data.name}, {s['doctor']} on {s['date']} at {s['time']}."}
    return {"ok": False, "reply": "Slot not found."}
