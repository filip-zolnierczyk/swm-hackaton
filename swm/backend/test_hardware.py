import cv2
import pyaudio

def check_audio():
    print("--- DIAGNOSTYKA AUDIO ---")
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    found = False
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            print(f"ID {i}: {p.get_device_info_by_host_api_device_index(0, i).get('name')}")
            found = True
    
    if not found:
        print("❌ Nie znaleziono mikrofonu!")
    p.terminate()

def check_video():
    print("\n--- DIAGNOSTYKA WIDEO ---")
    # Próbujemy indeksy od 0 do 2
    for i in range(3):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print(f"✅ Kamera o ID {i} DZIAŁA!")
                cv2.imshow(f'Test Kamery ID {i}', frame)
                print("Naciśnij dowolny klawisz w oknie obrazu, aby zamknąć...")
                cv2.waitKey(0)
                cap.release()
                cv2.destroyAllWindows()
                return i
            cap.release()
    print("❌ Nie znaleziono działającej kamery!")
    return None

if __name__ == "__main__":
    check_audio()
    check_video()