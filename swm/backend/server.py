import asyncio
import json
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 1. KONFIGURACJA CORS (Bardzo ważne!)
# Pozwala Twojemu frontendowi (np. localhost:5173) łączyć się z tym serwerem
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # W produkcji podaj konkretny adres frontendu
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Przykładowa baza "zmochowanych" faktów
MOCK_DATABASE = [
    {
        "status": "true",
        "quote": "Deficyt budżetowy w tym roku wyniesie 5%.",
        "analysis": "Zgodnie z najnowszym raportem Ministerstwa Finansów, prognoza ta pokrywa się z rzeczywistymi wydatkami."
    },
    {
        "status": "false",
        "quote": "Polska jest jedynym krajem w UE bez dostępu do morza.",
        "analysis": "To ewidentny błąd. Polska ma ponad 400 km linii brzegowej nad Morzem Bałtyckim."
    },
    {
        "status": "mixed",
        "quote": "Ceny paliw spadły o połowę w ciągu miesiąca.",
        "analysis": "Ceny faktycznie spadły, ale jedynie o 5-8%, a nie o 50% jak sugeruje wypowiedź."
    },
    {
        "status": "true",
        "quote": "AI potrafi generować kod w języku Python.",
        "analysis": "Modele LLM wykazują wysoką skuteczność w generowaniu i debugowaniu kodu Python."
    }
]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Frontend połączony przez WebSocket")
    
    try:
        # Wysyłamy pierwszy kafelek niemal natychmiast
        initial_fact = random.choice(MOCK_DATABASE)
        await websocket.send_json(initial_fact)
        
        # Pętla symulująca działanie AI (np. co 7 sekund wpada nowa ocena)
        while True:
            await asyncio.sleep(7)
            fact = random.choice(MOCK_DATABASE)
            
            # To jest moment, w którym "przesyłasz" kafelek do frontendu
            await websocket.send_json(fact)
            print(f"🚀 Wysłano kafelek: {fact['status']}")

    except WebSocketDisconnect:
        print("❌ Frontend rozłączony")
    except Exception as e:
        print(f"⚠️ Błąd: {e}")

# Endpoint dla WebRTC (żeby frontend nie sypał błędami w konsoli)
@app.post("/offer")
async def offer(request: dict):
    # Na razie zwracamy pustą odpowiedź, żeby frontend "wiedział", że serwer żyje
    return {"message": "Endpoint wideo gotowy, ale nie przesyła jeszcze obrazu"}

if __name__ == "__main__":
    import uvicorn
    # Uruchamiamy na porcie 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)