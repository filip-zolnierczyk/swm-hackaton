# Fact-Check Live - Setup Guide

## Overview

**Fact-Check Live** requires two components:
- **Backend**: Python server (processes audio, connects to Gemini API)
- **Frontend**: React web interface (displays results in real-time)

Two setup scenarios are provided below.

---

## Setup for Stream Host (Running Backend + Frontend Locally)

If you're operating the system that captures audio/video and runs the fact-checking engine:

### 1. Backend Setup

```bash
cd swm/backend

python setup.py
```

Follow the prompts:
- Enter your GEMINI_API_KEY (get from https://aistudio.google.com)
- Confirm server port (default: 8000)
- Choose whether to run hardware diagnostics

This creates `.env` with configuration.

### 2. Frontend Setup

```bash
cd swm/frontend

npm install
```

The frontend will use local settings (127.0.0.1:8000) by default.

### 3. Start the System

Terminal 1 - Backend:
```bash
cd swm/backend
python server.py
```

Terminal 2 - Frontend:
```bash
cd swm/frontend
npm run dev
```

Access the interface at `http://localhost:5173`

---

## Setup for Viewer (Frontend Only on Different Machine)

If you're accessing a running Fact-Check Live system on another machine:

### 1. Get Backend Address

Ask the system operator for:
- Backend machine IP address
- Port number (default: 8000)

Example: `192.168.1.100:8000`

### 2. Frontend Setup

```bash
cd swm/frontend

npm install
```

Create `.env` file with:
```
VITE_API_HOST=http://192.168.1.100:8000
VITE_WS_HOST=ws://192.168.1.100:8000
```

Replace `192.168.1.100` with actual backend IP.

### 3. Start Frontend

```bash
npm run dev
```

Access at `http://localhost:5173`

---

## Environment Variables

### Backend (.env)

```
GEMINI_API_KEY=<your-gemini-api-key>
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

**SERVER_HOST options:**
- `0.0.0.0` - Accept connections from any machine (recommended)
- `127.0.0.1` - Local machine only

### Frontend (.env)

```
VITE_API_HOST=http://backend-ip:8000
VITE_WS_HOST=ws://backend-ip:8000
```

---

## Hardware Requirements

### For Stream Host

- **Microphone**: Built-in or USB microphone (auto-detected)
- **Camera**: Built-in or USB webcam (auto-detected, or test pattern used as fallback)
- **Network**: Stable internet connection for Gemini API

### For Viewer

- Just a web browser
- Network connection to backend machine

---

## Troubleshooting

### Backend Issues

**"GEMINI_API_KEY not found"**
- Create `.env` in `swm/backend/`
- Add your API key from https://aistudio.google.com

**"Port 8000 already in use"**
- Edit `.env` and change `SERVER_PORT` to an available port
- Update `VITE_API_HOST` accordingly on all frontends

**"Backend runs but frontend can't connect"**
- Verify backend is accessible: `curl http://backend-ip:8000/docs`
- Check firewall allows port 8000
- Confirm `VITE_API_HOST` points to correct backend IP

### Hardware Issues

**Audio not detected:**
```bash
python swm/backend/test_hardware.py
```
Lists available audio devices. On Windows/Linux, may need manual configuration.

**Camera not detected:**
Run the same diagnostic above. If unavailable, system uses test pattern.

### Frontend Issues

**"Cannot connect to backend" from browser**
- Backend must be running first
- Check network connectivity between machines
- Verify firewall/NAT allows WebSocket connections

**Port 5173 already in use**
- Vite will auto-increment to 5174, 5175, etc.
- Or change in `vite.config.ts`

---

## Getting GEMINI_API_KEY

1. Visit https://aistudio.google.com
2. Sign in with Google account
3. Click "Get API Key"
4. Copy the key to `.env`:
```
GEMINI_API_KEY=your-key-here
```

---

## Common Configurations

### Local Machine Only
```
VITE_API_HOST=http://127.0.0.1:8000
VITE_WS_HOST=ws://127.0.0.1:8000
SERVER_HOST=127.0.0.1
```

### LAN Access (Host on 192.168.1.100)
```
# Backend .env
SERVER_HOST=0.0.0.0

# Frontend .env (on any machine in network)
VITE_API_HOST=http://192.168.1.100:8000
VITE_WS_HOST=ws://192.168.1.100:8000
```

### Docker/Remote Server
```
# Backend .env
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Frontend .env
VITE_API_HOST=https://myserver.com/api
VITE_WS_HOST=wss://myserver.com
```

---

## Quick Diagnostics

Check if everything is working:

```bash
# Test backend is running
curl http://backend-ip:8000/docs

# Test hardware
python swm/backend/test_hardware.py

# Test WebSocket connection (from browser console)
ws = new WebSocket('ws://backend-ip:8000/ws')
ws.onopen = () => console.log('Connected')
```

---

## Support

For issues or questions, refer to the main README.md or check the application logs.
