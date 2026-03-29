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


def load_local_env() -> None:
    # Load environment variables from .env file
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
    raise RuntimeError("GEMINI_API_KEY not found. Set GEMINI_API_KEY in .env")

MODEL = "models/gemini-3.1-flash-live-preview"
WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={API_KEY}"
RATE = 16000
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pcs = set()
clients = []


def create_video_player() -> MediaPlayer:
    # Platform-specific video capture setup
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

    # Linux/other fallback
    return MediaPlayer(
        "/dev/video0",
        format="v4l2",
        options={
            "video_size": "1280x720",
            "framerate": "30",
        },
    )


def create_audio_player() -> MediaPlayer:
    # Platform-specific audio input setup
    system = platform.system()

    if system == "Darwin":
        # macOS: "none:0" means first audio device only
        return MediaPlayer("none:0", format="avfoundation")

    if system == "Windows":
        return MediaPlayer("audio=Microphone Array (AMD Audio Device)", format="dshow")

    # Linux/other fallback
    return MediaPlayer("default", format="pulse")


@app.post("/offer")
async def offer(request: Request):
    # WebRTC offer from frontend - establish peer connection
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    # Video track with fallback to test pattern
    try:
        video_player = create_video_player()
        pc.addTrack(video_player.video)
        print("Video device connected")
    except (OSError, RuntimeError, ValueError) as e:
        print(f"Video device failed, using test pattern: {e}")
        test_player = MediaPlayer('testsrc', format='lavfi', options={'size': '1280x720', 'rate': '30'})
        pc.addTrack(test_player.video)

    # Audio track with fallback to silent track
    try:
        audio_player = create_audio_player()
        pc.addTrack(audio_player.audio)
        print("Audio device connected")
    except (OSError, RuntimeError, ValueError) as e:
        print(f"Audio device failed, using silent track: {e}")
        null_audio = MediaPlayer('anullsrc', format='lavfi')
        pc.addTrack(null_audio.audio)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return JSONResponse({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # WebSocket connection for sending fact-check results to frontend
    await ws.accept()
    clients.append(ws)
    print("Frontend connected")

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)
        print("Frontend disconnected")


async def broadcast(data):
    # Send fact-check result to all connected frontends
    dead_clients = []

    for client in clients:
        try:
            await client.send_json(data)
        except (RuntimeError, ConnectionError) as e:
            print(f"Failed to send to client: {e}")
            dead_clients.append(client)

    for dc in dead_clients:
        clients.remove(dc)


audio_queue = asyncio.Queue()


def audio_callback(indata, frames, time, status):
    # Capture audio from system microphone and convert to PCM format
    if status:
        print(f"Audio status: {status}")
    audio_bytes = (indata * 32767).astype("int16").tobytes()
    asyncio.run_coroutine_threadsafe(audio_queue.put(audio_bytes), loop)


grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)


async def send_config(ws):
    # Send Gemini API configuration for fact-checking
    config = {
        "setup": {
            "model": MODEL,
            "systemInstruction": {
                "parts": [{
                    "text": """
You are a fact-checking system. The statements will be in Polish.
Do not comment on every statement—only respond to specific claims.
If a statement does not contain a claim, respond with "uncertain" and a lower confidence.
If the claim is true, respond with "true". If false, respond with "false".
If it is a personal opinion that is very difficult to verify, respond with "uncertain".
If you are not sure whether you fully understood the claim or it's very bungled up, lower your confidence.
All JSON fields, including "claim", have to be in English.
For territorial disputes, say "uncertain" and explain the different perspectives.

Always respond ONLY with valid JSON:

{
"claim": string,
"verdict": "true" | "false" | "uncertain",
"confidence": number (0-1),
"explanation": string
}

Do not add any text outside the JSON.
Be skeptical.

"""
                }]
            },
            "generationConfig": {
                "responseModalities": ["AUDIO"]
            },
            "outputAudioTranscription": {}
        }
    }
    print("Sending Gemini config...")
    await ws.send(json.dumps(config))


async def send_audio(ws):
    # Stream audio from queue to Gemini API
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


def safe_parse_json(text):
    # Safely parse JSON from text, extracting if mixed with other content
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                return None
    return None


async def receive(ws):
    # Receive fact-check results from Gemini and broadcast to frontend
    pending_json = None
    async for msg in ws:
        data = json.loads(msg)
        if "setupComplete" in data:
            print("Gemini setup complete")
        if "serverContent" in data:
            sc = data["serverContent"]
            if "inputTranscription" in sc:
                # User's spoken input
                print(f"Input: {sc['inputTranscription']['text']}")
            if "outputTranscription" in sc:
                # Gemini's fact-check result
                raw = sc["outputTranscription"]["text"]
                parsed = safe_parse_json(raw)
                if parsed:
                    pending_json = parsed
            if sc.get("turnComplete"):
                if pending_json:
                    print("Fact-check result:")
                    print(json.dumps(pending_json, indent=2, ensure_ascii=False))
                    confidence = pending_json.get("confidence", 0)
                    try:
                        confidence = float(confidence)
                    except (TypeError, ValueError):
                        confidence = 0.0

                    # Skip low-confidence results
                    if confidence <= 0.50:
                        print(f"Skipping low confidence result (confidence={confidence:.2f})")
                        pending_json = None
                        print("Turn complete")
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
                    pending_json = None
                print("Turn complete")


async def main():
    # Main loop: connect to Gemini, send audio, receive results
    global loop
    loop = asyncio.get_event_loop()
    print("Connecting to Gemini...")
    async with websockets.connect(WS_URL) as ws:
        print("Connected to Gemini")
        await send_config(ws)
        stream = sd.InputStream(
            samplerate=RATE,
            channels=1,
            callback=audio_callback
        )
        stream.start()
        print("Audio input started")
        await asyncio.gather(
            send_audio(ws),
            receive(ws)
        )


if __name__ == "__main__":
    # Start Gemini connection thread and FastAPI server
    def run_async():
        asyncio.run(main())
    threading.Thread(target=run_async, daemon=True).start()
    print(f"Starting server at {SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
