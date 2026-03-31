import cv2
import pyaudio
import platform


def check_audio(verbose: bool = True):
    # Detect and list available audio devices
    # Returns first device ID if found, None otherwise
    if verbose:
        print("AUDIO DEVICES")

    try:
        p = pyaudio.PyAudio()
        info = p.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')

        devices = []
        for i in range(0, numdevices):
            device_info = p.get_device_info_by_host_api_device_index(0, i)
            if device_info.get('maxInputChannels') > 0:
                name = device_info.get('name')
                if verbose:
                    print(f"  ID {i}: {name}")
                devices.append((i, name))

        p.terminate()

        if not devices:
            if verbose:
                print("No audio devices found")
            return None

        if verbose:
            print(f"Found {len(devices)} device(s)")

        return devices[0][0] if devices else None

    except Exception as e:
        if verbose:
            print(f"Error during audio detection: {e}")
        return None


def check_video(verbose: bool = True, show_preview: bool = False):
    # Detect and test available video devices
    # Returns device ID if found, None otherwise
    if verbose:
        print("VIDEO DEVICES")

    try:
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    if verbose:
                        print(f"  ID {i}: OK ({frame.shape[1]}x{frame.shape[0]})")

                    if show_preview and platform.system() != "Linux":
                        try:
                            cv2.imshow(f'Camera {i}', frame)
                            print("  Press any key to close preview...")
                            cv2.waitKey(0)
                            cv2.destroyAllWindows()
                        except Exception as e:
                            if verbose:
                                print(f"  Preview unavailable: {e}")

                    cap.release()
                    return i

                cap.release()

        if verbose:
            print("No working video devices found")
        return None

    except Exception as e:
        if verbose:
            print(f"Error during video detection: {e}")
        return None


def get_system_info():
    return {
        "system": platform.system(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


if __name__ == "__main__":
    info = get_system_info()
    print(f"System: {info['system']}\n")
    check_audio(verbose=True)
    check_video(verbose=True, show_preview=True)
