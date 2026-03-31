import os
import sys
import socket
from pathlib import Path
import platform

# Setup script for Fact-Check Live application
# Detects hardware capabilities and generates configuration files

backend_path = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_path))

try:
    from test_hardware import check_audio, check_video
except ImportError:
    print("Error: test_hardware.py not found")
    sys.exit(1)


def get_local_ip():
    # Detect machine IP for network access
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def setup_backend_env():
    env_path = backend_path / ".env"

    if env_path.exists():
        print(f"Backend .env already exists at {env_path}")
        return

    api_key = input("Enter GEMINI_API_KEY (press Enter to skip): ").strip()
    server_port = input("Server port [8000]: ").strip() or "8000"

    content = f"""GEMINI_API_KEY={api_key or 'PLACEHOLDER_API_KEY'}
SERVER_HOST=0.0.0.0
SERVER_PORT={server_port}
"""

    env_path.write_text(content)
    print(f"Created .env at {env_path}")


def setup_frontend_env():
    frontend_path = backend_path.parent / "frontend"
    env_path = frontend_path / ".env"

    if env_path.exists():
        print(f"Frontend .env already exists at {env_path}")
        return

    local_ip = get_local_ip()

    print(f"\nDetected local IP: {local_ip}")
    print("Use 127.0.0.1 for local-only access, or your machine IP for remote access")

    api_host = input(f"API Host [http://{local_ip}:8000]: ").strip() or f"http://{local_ip}:8000"
    ws_host = input(f"WebSocket Host [ws://{local_ip}:8000]: ").strip() or f"ws://{local_ip}:8000"

    content = f"""VITE_API_HOST={api_host}
VITE_WS_HOST={ws_host}
"""

    env_path.write_text(content)
    print(f"Created .env at {env_path}")


def check_hardware():
    print("\n" + "="*50)
    print("HARDWARE DIAGNOSTICS")
    print("="*50)

    system = platform.system()
    print(f"OS: {system}")

    print()
    check_audio()
    print()
    result = check_video()

    print("\n" + "="*50)

    if not result:
        print("No video device found - test pattern will be used")
    else:
        print(f"Video device {result} is working")


def main():
    print("""
=====================================
Fact-Check Live - Setup
=====================================
""")

    print("Setting up backend configuration...")
    setup_backend_env()

    print("\nSetting up frontend configuration...")
    setup_frontend_env()

    print("\n" + "="*50)
    response = input("Run hardware diagnostics? [y/n]: ").strip().lower()
    if response == 'y':
        check_hardware()

    print("\nSetup complete!")
    print("\nNext steps:")
    print("  Backend:  python server.py")
    print("  Frontend: cd swm/frontend && npm run dev")


if __name__ == "__main__":
    main()
