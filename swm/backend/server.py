import asyncio
import json
import platform
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Przechowujemy aktywne połączenia WebRTC
pcs = set()


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

# Pozostawiamy stary endpoint WebSocket dla kafelków
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except:
        pass

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)