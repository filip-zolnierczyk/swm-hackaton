import React, { useEffect, useRef, useState } from 'react';
import './index.css';

// --- TYPY DANYCH ---
interface FactCheck {
  id?: number;
  status: 'true' | 'false' | 'mixed';
  quote: string;
  analysis: string;
}

const App: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [factChecks, setFactChecks] = useState<FactCheck[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<string>('Inicjalizacja...');
  const [streamStarted, setStreamStarted] = useState<boolean>(false);

  // --- FUNKCJA ROZPOCZĘCIA STRUMIENIA ---
  const handleStartStream = async () => {
    if (videoRef.current && !streamStarted) {
      setStreamStarted(true);
      await startStreaming(videoRef.current);
    }
  };

  // --- FUNKCJA TRANSMISJI WIDEO (WebRTC) ---
  const startStreaming = async (videoElement: HTMLVideoElement) => {
    try {
      console.log("🚀 Inicjowanie WebRTC: Wysyłanie oferty do Pythona...");
      const pc = new RTCPeerConnection();

      // Odbieranie strumienia (wideo/audio) z Pythona
      pc.ontrack = (event) => {
      console.log(`📥 Otrzymano track: ${event.track.kind}`);
      if (videoElement) {
        // Jeśli wideo nie ma jeszcze obiektu stream, utwórz go
        if (!videoElement.srcObject) {
          videoElement.srcObject = new MediaStream();
        }
        // Dodaj przychodzący track (audio lub wideo) do naszego strumienia
        const stream = videoElement.srcObject as MediaStream;
        stream.addTrack(event.track);
      }
    };

      // Deklarujemy, że chcemy tylko odbierać dane
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // Wysyłamy ofertę SDP do endpointu /offer w Pythonie
      const response = await fetch('http://127.0.0.1:8000/offer', {
        method: 'POST',
        body: JSON.stringify({
          sdp: pc.localDescription?.sdp,
          type: pc.localDescription?.type,
        }),
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) throw new Error("Serwer Python odrzucił ofertę WebRTC");

      const answer = await response.json();
      await pc.setRemoteDescription(new RTCSessionDescription(answer));
      console.log("✅ Połączenie WebRTC ustanowione!");
    } catch (err) {
      console.error("❌ Błąd WebRTC:", err);
    }
  };

  // --- OBSŁUGA POŁĄCZENIA (WebSocket + Start Mediów) ---
  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimeout: number;

    const connect = () => {
      console.log("Próba połączenia z WebSocket...");
      socket = new WebSocket('ws://127.0.0.1:8000/ws');

      socket.onopen = () => {
        console.log("✅ WebSocket Połączony!");
        setConnectionStatus('Connected');
        
        // Nie odpalamy strumienia automatycznie, czekamy na interakcję użytkownika
      };

      socket.onmessage = (event) => {
        try {
          const data: FactCheck = JSON.parse(event.data);
          // Dodajemy nowy fakt na górę listy
          setFactChecks(prev => [{ ...data, id: Date.now() }, ...prev]);
        } catch (err) {
          console.error("Błąd parsowania danych kafelka:", err);
        }
      };

      socket.onerror = () => {
        setConnectionStatus('Błąd połączenia');
      };

      socket.onclose = () => {
        console.log("🔌 Połączenie zamknięte. Reconnect za 2s...");
        setConnectionStatus('Rozłączono');
        reconnectTimeout = window.setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      if (socket) socket.close();
      clearTimeout(reconnectTimeout);
    };
  }, []);

  return (
    <div className="app-wrapper">
      
      {/* NAGŁÓWEK */}
      <header className="main-header">
        <div>
          <h1 className="header-title">Fact-Check Live <span className="dot-live">●</span></h1>
          <p style={{ fontWeight: 'bold', textTransform: 'uppercase', color: '#4b5563', margin: 0 }}>Real-time Stream Analysis System</p>
        </div>
        <div className="header-info">
          <div className="addr-badge">ADDR: 127.0.0.1:8000</div>
          <div className="status-text" style={{ color: connectionStatus === 'Connected' ? '#16a34a' : '#dc2626' }}>
            Status: {connectionStatus}
          </div>
        </div>
      </header>

      {/* SEKCJA GŁÓWNA */}
      <main className="content-grid">
        
        {/* OKNO WIDEO */}
        <div className="video-box">
          <video ref={videoRef} autoPlay playsInline muted={false} />
          {!streamStarted && connectionStatus === 'Connected' && (
            <button 
              className="start-stream-btn" 
              onClick={handleStartStream}
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                zIndex: 10
              }}
            >
              Start Stream
            </button>
          )}
          {connectionStatus !== 'Connected' && (
            <div className="waiting-overlay">Oczekiwanie na sygnał...</div>
          )}
        </div>

        {/* PANEL KAFELKÓW */}
        <div className="fact-panel">
          {factChecks.length === 0 ? (
            <div className="no-data">No Data<br/>Detected</div>
          ) : (
            factChecks.map((item) => (
              <div 
                key={item.id} 
                className={`fact-card card-${item.status}`}
              >
                <div className="card-header">
                  <span className="card-verdict">
                    {item.status === 'true' ? '✓ True' : item.status === 'false' ? '✗ False' : '⚠ Mixed'}
                  </span>
                  <span className="card-live-label">LIVE</span>
                </div>
                <p className="card-quote">"{item.quote}"</p>
                <div className="card-analysis-box">
                    <p className="card-analysis-text">{item.analysis}</p>
                </div>
              </div>
            ))
          )}
        </div>

      </main>

      <footer className="footer">
        Engine: Python AI / WebRTC Stream / React Interface
      </footer>
    </div>
  );
};

export default App;
