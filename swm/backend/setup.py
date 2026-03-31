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

    # Read existing env if it exists
    existing_api_key = None
    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('GEMINI_API_KEY='):
                        existing_api_key = line.split('=', 1)[1].strip()
                        break
        except Exception:
            pass

    # Ask for API key only if not already set
    if existing_api_key:
        print(f"Found existing GEMINI_API_KEY")
        api_key = existing_api_key
    else:
        api_key = input("Enter GEMINI_API_KEY (press Enter to skip): ").strip()

    server_port = input("Server port [8000]: ").strip() or "8000"

    content = f"""GEMINI_API_KEY={api_key or 'PLACEHOLDER_API_KEY'}
SERVER_HOST=0.0.0.0
SERVER_PORT={server_port}
"""

    env_path.write_text(content)
    if env_path.exists() and existing_api_key:
        print(f"Updated .env at {env_path}")
    else:
        print(f"Created .env at {env_path}")


def setup_frontend_env(is_host=True):
    frontend_path = backend_path.parent / "frontend"
    env_path = frontend_path / ".env"

    local_ip = get_local_ip()

    if is_host:
        # HOST: connect to local backend
        default_api_host = f"http://{local_ip}:8000"
        default_ws_host = f"ws://{local_ip}:8000"
    else:
        # CLIENT: ask for backend IP
        print("\nEnter the HOST machine's IP address (the one running backend)")
        print("Example: 192.168.1.100 or 10.0.0.5")
        backend_ip = input("Backend machine IP: ").strip()
        default_api_host = f"http://{backend_ip}:8000"
        default_ws_host = f"ws://{backend_ip}:8000"

    api_host = input(f"API Host [{default_api_host}]: ").strip() or default_api_host
    ws_host = input(f"WebSocket Host [{default_ws_host}]: ").strip() or default_ws_host

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

    # Ask if user is the host (streamer) or client (viewer)
    print("\nAre you the HOST (running backend + frontend)?")
    is_host = input("Enter 'y' for host, 'n' for viewer client [y]: ").strip().lower() != 'n'

    if is_host:
        print("\n" + "="*50)
        print("SETUP: Stream Host (Backend + Frontend)")
        print("="*50)

        print("\nSetting up backend configuration...")
        setup_backend_env()

        print("\nSetting up frontend configuration...")
        setup_frontend_env(is_host=True)

        print("\n" + "="*50)
        response = input("Run hardware diagnostics? [y/n]: ").strip().lower()
        if response == 'y':
            check_hardware()

        local_ip = get_local_ip()
        print("\nSetup complete!")
        print("\nNext steps:")
        print("  Terminal 1 - Backend:  cd swm/backend && python server.py")
        print("  Terminal 2 - Frontend: cd swm/frontend && npm run dev")
        print(f"\nAccess frontend locally at: http://localhost:5173")
        print(f"\nOther devices can view the stream if they:")
        print(f"  1. Run setup.py on their machine and choose 'n' for client")
        print(f"  2. Enter this machine's IP: {local_ip}")
        print(f"  3. Run their own frontend: npm run dev")
    else:
        print("\n" + "="*50)
        print("SETUP: Viewer Client (Frontend Only)")
        print("="*50)

        print("\nSetting up frontend configuration...")
        setup_frontend_env(is_host=False)

        print("\nSetup complete!")
        print("\nNext steps:")
        print("  cd swm/frontend && npm run dev")
        print(f"\nFrontend will be at: http://localhost:5173")


if __name__ == "__main__":
    main()
