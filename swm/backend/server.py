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
import httpx


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

# Live API model (used by the real-time WebSocket normal mode)
MODEL = "models/gemini-3.1-flash-live-preview"
WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={API_KEY}"

# REST model for thorough mode (generateContent + Google Search grounding)
THOROUGH_MODEL = "gemini-2.5-flash"
THOROUGH_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{THOROUGH_MODEL}:generateContent?key={API_KEY}"

RATE = 16000
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# System prompt for normal mode (single claim per response)
SYSTEM_PROMPT = """
You are a fact-checking system that responds in English only.
Respond to specific claims made in the conversation.
Be aggressive in identifying verifiable claims and checking them - you don't have to wait until a person has stopped talking to respond.
You must respond in the middle of a person's statement if you identify a claim that can be checked.
If a statement does not contain a verifiable claim, respond with "uncertain" and lower confidence.
If the claim is true, respond with "true". If false, respond with "false".
If it is a personal opinion that is very difficult to verify, respond with "uncertain".
If you are not sure whether you fully understood the claim, lower your confidence.
All JSON fields must be in English.
For territorial disputes, say "uncertain" and explain the different perspectives.

Always respond ONLY with valid JSON:

{
"claim": string,
"verdict": "true" | "false" | "uncertain",
"confidence": number (0-1),
"explanation": string
}

Do not add any text outside the JSON.
Be skeptical. Check claims concisely.
"""

# System prompt for thorough mode (extract and check multiple claims)
THOROUGH_SYSTEM_PROMPT = """
You are a fact-checking system that responds in English only.
Extract ALL verifiable claims from the given text and fact-check each one.
If the text contains multiple claims, return an array with one entry per claim.
Do not comment on every statement—only extract claims that are verifiable.
If a claim is true, respond with "true". If false, respond with "false".
If it is a personal opinion or very difficult to verify, respond with "uncertain".
All JSON fields must be in English.
For territorial disputes, say "uncertain" and explain the different perspectives.

Always respond ONLY with valid JSON as an array:

[
{
"claim": string,
"verdict": "true" | "false" | "uncertain",
"confidence": number (0-1),
"explanation": string
}
]

Return an empty array [] if there are no verifiable claims.
Do not add any text outside the JSON.
Be skeptical and extract all claimable statements, even partial ones.
"""

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


async def thorough_fact_check(claim: str) -> list[dict] | None:
    # Send claim to generateContent REST API with Google Search grounding
    # Returns a list of fact-checks (one per extracted claim)
    payload = {
        "systemInstruction": {
            "parts": [{"text": THOROUGH_SYSTEM_PROMPT}]
        },
        "contents": [{
            "parts": [{"text": claim}]
        }],
        "tools": [{"google_search": {}}]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(THOROUGH_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        print(f"Thorough raw response: {raw_text[:200]}")
        parsed = safe_parse_json(raw_text)

        # Ensure parsed is a list
        if not isinstance(parsed, list):
            if isinstance(parsed, dict):
                parsed = [parsed]
            else:
                return None

        # Extract sources from grounding metadata (same for all claims)
        sources = []
        if "groundingMetadata" in data["candidates"][0]:
            grounding = data["candidates"][0]["groundingMetadata"]
            if "groundingAttributions" in grounding:
                for attr in grounding["groundingAttributions"][:5]:
                    url = attr.get("web", {}).get("uri", "")
                    title = attr.get("web", {}).get("title", "")
                    if url:
                        sources.append({"title": title or url, "url": url})
                    elif "segment" in attr and "text" in attr["segment"]:
                        text = attr["segment"]["text"].strip()
                        if text and len(text) > 5:
                            sources.append({"text": text})
            if not sources and "searchEntryPoint" in grounding:
                rendered = grounding["searchEntryPoint"].get("renderedContent", "")
                if rendered:
                    sources.append({"html": rendered})

        # Attach sources to each claim
        return [{**item, "sources": sources} for item in parsed]

    except httpx.HTTPStatusError as e:
        print(f"Thorough mode HTTP error {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        print(f"Thorough mode error: {e}")
        return None


@app.post("/thorough")
async def thorough_endpoint(request: Request):
    # Receive claim, fact-check it, return response (do not broadcast)
    body = await request.json()
    claim = body.get("text", "").strip()

    if not claim:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    print(f"Thorough check requested: {claim[:100]}")
    results = await thorough_fact_check(claim)

    if not results:
        return JSONResponse({"error": "Failed to parse Gemini response"}, status_code=500)

    verdict_map = {"true": "true", "false": "false", "uncertain": "mixed"}

    # Convert all results to payload format and return as array
    payloads = [
        {
            "status": verdict_map.get(result.get("verdict"), "mixed"),
            "quote": result.get("claim", claim),
            "analysis": result.get("explanation", ""),
            "sources": result.get("sources", [])
        }
        for result in results
    ]

    # If single result, return as object for backwards compatibility; otherwise array
    return JSONResponse(payloads if len(payloads) > 1 else payloads[0])


audio_queue = asyncio.Queue()


def audio_callback(indata, frames, time, status):
    # Capture audio from system microphone and convert to PCM format
    if status:
        print(f"Audio status: {status}")
    audio_bytes = (indata * 32767).astype("int16").tobytes()
    asyncio.run_coroutine_threadsafe(audio_queue.put(audio_bytes), loop)


async def send_config(ws):
    # Send Gemini Live API configuration for fact-checking
    config = {
        "setup": {
            "model": MODEL,
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
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
    # Handles both objects {} and arrays []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Try to match either array or object pattern
        match = re.search(r"\[.*\]|\{.*\}", text, re.DOTALL)
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
                    # Handle both single object and array responses
                    results = pending_json if isinstance(pending_json, list) else [pending_json]

                    for result in results:
                        print("Fact-check result:")
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                        confidence = result.get("confidence", 0)
                        try:
                            confidence = float(confidence)
                        except (TypeError, ValueError):
                            confidence = 0.0

                        # Skip low-confidence results
                        if confidence <= 0.50:
                            print(f"Skipping low confidence result (confidence={confidence:.2f})")
                            continue

                        verdict_map = {
                            "true": "true",
                            "false": "false",
                            "uncertain": "mixed"
                        }
                        payload = {
                            "status": verdict_map.get(result.get("verdict"), "mixed"),
                            "quote": result.get("claim", ""),
                            "analysis": result.get("explanation", "")
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
