import asyncio
import websockets
import json
import base64
import os
import sounddevice as sd
import re
import threading
import platform
from pathlib import Path
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
import uvicorn

from google.genai import types

# ================================
# 🔐 CONFIG
# ================================
def load_local_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_local_env()
API_KEY = os.getenv("GEMINI_API_KEY", "")
if not API_KEY:
    raise RuntimeError("Brak GEMINI_API_KEY. Ustaw klucz w swm/backend/.env.")

MODEL = "models/gemini-3.1-flash-live-preview"
WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={API_KEY}"
RATE = 16000

# ================================
# 🌐 FASTAPI + WS + WebRTC
# ================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Przechowujemy aktywne połączenia WebRTC
pcs = set()
clients = []

def create_video_player() -> MediaPlayer:
    system = platform.system()

    if system == "Darwin":
        # macOS: avfoundation uses "video_index:audio_index"
        return MediaPlayer(
            "0:none",
            format="avfoundation",
            options={
                "video_size": "1280x720",
                "framerate": "30",
            },
        )

    if system == "Windows":
        return MediaPlayer(
            "video=0",
            format="dshow",
            options={
                "video_size": "1280x720",
                "framerate": "30",
            },
        )

    # Linux/other fallback (camera index 0)
    return MediaPlayer(
        "/dev/video0",
        format="v4l2",
        options={
            "video_size": "1280x720",
            "framerate": "30",
        },
    )


def create_audio_player() -> MediaPlayer:
    system = platform.system()

    if system == "Darwin":
        # macOS: "none:0" means first audio device only.
        return MediaPlayer("none:0", format="avfoundation")

    if system == "Windows":
        return MediaPlayer("audio=Microphone Array (AMD Audio Device)", format="dshow")

    # Linux/other fallback
    return MediaPlayer("default", format="pulse")

@app.post("/offer")
async def offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    # --- OBSŁUGA WIDEO ---
    try:
        # Próbujemy Twoją kamerę
        video_player = create_video_player()
        pc.addTrack(video_player.video)
        print("✅ Kamera podpięta!")
    except Exception as e:
        print(f"⚠️ Kamera padła, daję pasy testowe: {e}")
        test_player = MediaPlayer('testsrc', format='lavfi', options={'size': '1280x720', 'rate': '30'})
        pc.addTrack(test_player.video)

    # --- OBSŁUGA AUDIO (Zabezpieczona) ---
    try:
        audio_player = create_audio_player()
        pc.addTrack(audio_player.audio)
        print("✅ Mikrofon podpięty!")
    except Exception as e:
        print(f"⚠️ Mikrofon nie działa ({e}). Wysyłam ciszę, żeby nie wywalić błędu.")
        # Generujemy "ciszę", żeby WebRTC miało jakikolwiek track audio
        null_audio = MediaPlayer('anullsrc', format='lavfi')
        pc.addTrack(null_audio.audio)

    # --- HANDSHAKE ---
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return JSONResponse({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    print("🌐 Frontend connected")

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)
        print("❌ Frontend disconnected")


async def broadcast(data):
    dead_clients = []

    for client in clients:
        try:
            await client.send_json(data)
        except:
            dead_clients.append(client)

    for dc in dead_clients:
        clients.remove(dc)


# ================================
# 🎤 AUDIO
# ================================
audio_queue = asyncio.Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print("⚠️ Audio status:", status)
    audio_bytes = (indata * 32767).astype("int16").tobytes()
    asyncio.run_coroutine_threadsafe(audio_queue.put(audio_bytes), loop)


# ================================
# 🤖 GEMINI CONFIG
# ================================
grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)

async def send_config(ws):
    config = {
        "setup": {
            "model": MODEL,
            "systemInstruction": {
                "parts": [{
                    "text": """
Jesteś systemem do weryfikacji faktów. Wypowiedzi będą po polsku.
Nie komentuj każdej wypowiedzi, tylko odpowiadaj na konkretne roszczenia (claims).
Jeśli wypowiedź nie zawiera roszczenia, odpowiedz "uncertain" z obniżonym confidence.
Jeśli roszczenie jest prawdziwe, odpowiedz "true". Jeśli fałszywe, odpowiedz "false".
Jeśli prywatną opinię bardzo ciężko zweryfikować, odpowiedz "uncertain".
Jeśli nie jesteś pewien czy dobrze oddasz o co chodziło, zmniejszyj swoją pewność (confidence).

Zawsze odpowiadaj WYŁĄCZNIE poprawnym JSON-em:

{
  "claim": string,
  "verdict": "true" | "false" | "uncertain",
  "confidence": number (0-1),
  "explanation": string
}

Nie dodawaj żadnego tekstu poza JSON.
Bądź sceptyczny.
"""
                }]
            },
            "generationConfig": {
                "responseModalities": ["AUDIO"]
            },
            "outputAudioTranscription": {}
        }
    }
    print("📤 Sending setup...")
    await ws.send(json.dumps(config))

async def send_audio(ws):
    while True:
        chunk = await audio_queue.get()
        encoded = base64.b64encode(chunk).decode()
        msg = {
            "realtimeInput": {
                "audio": {
                    "data": encoded,
                    "mimeType": "audio/pcm;rate=16000"
                }
            }
        }
        await ws.send(json.dumps(msg))


# ================================
# 🧠 JSON SAFE PARSER
# ================================
def safe_parse_json(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                return None
    return None


# ================================
# 📥 RECEIVE + BROADCAST
# ================================
async def receive(ws):
    pending_json = None  # 🔥 trzymamy tylko finalny wynik
    async for msg in ws:
        data = json.loads(msg)
        if "setupComplete" in data:
            print("✅ SETUP COMPLETE")
        if "serverContent" in data:
            sc = data["serverContent"]
            if "inputTranscription" in sc:
                print("🧑 YOU:", sc["inputTranscription"]["text"])
            if "outputTranscription" in sc:
                raw = sc["outputTranscription"]["text"]
                parsed = safe_parse_json(raw)
                if parsed:
                    pending_json = parsed  # 🔥 nadpisujemy (stream → final)
            if sc.get("turnComplete"):
                if pending_json:
                    print("\n✅ FACT CHECK RESULT:")
                    print(json.dumps(pending_json, indent=2, ensure_ascii=False))
                    confidence = pending_json.get("confidence", 0)
                    try:
                        confidence = float(confidence)
                    except (TypeError, ValueError):
                        confidence = 0.0

                    if confidence <= 0.49:
                        print(f"⏭️ SKIP TILE (confidence={confidence:.2f} <= 0.49)")
                        pending_json = None
                        print("✅ TURN COMPLETE\n")
                        continue

                    verdict_map = {
                        "true": "true",
                        "false": "false",
                        "uncertain": "mixed"
                    }
                    payload = {
                        "status": verdict_map.get(pending_json.get("verdict"), "mixed"),
                        "quote": pending_json.get("claim", ""),
                        "analysis": pending_json.get("explanation", "")
                    }
                    await broadcast(payload)
                    pending_json = None  # 🔥 reset na kolejny turn
                print("✅ TURN COMPLETE\n")


# ================================
# 🚀 GEMINI LOOP
# ================================
async def main():
    global loop
    loop = asyncio.get_event_loop()
    print("🔌 Connecting to Gemini...")
    async with websockets.connect(WS_URL) as ws:
        print("✅ Connected to Gemini")
        await send_config(ws)
        stream = sd.InputStream(
            samplerate=RATE,
            channels=1,
            callback=audio_callback
        )
        stream.start()
        print("🎤 Mic started")
        await asyncio.gather(
            send_audio(ws),
            receive(ws)
        )


# ================================
# ▶️ ENTRYPOINT
# ================================
if __name__ == "__main__":
    def run_async():
        asyncio.run(main())
    threading.Thread(target=run_async, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
