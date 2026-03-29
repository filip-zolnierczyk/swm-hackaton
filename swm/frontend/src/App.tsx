import React, { useEffect, useRef, useState } from 'react';
import './index.css';

interface FactCheck {
  id?: number;
  status: 'true' | 'false' | 'mixed';
  quote: string;
  analysis: string;
}

// Load config from environment variables
const API_HOST = import.meta.env.VITE_API_HOST || 'http://127.0.0.1:8000';
const WS_HOST = import.meta.env.VITE_WS_HOST || 'ws://127.0.0.1:8000';

const App: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [factChecks, setFactChecks] = useState<FactCheck[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<string>('Initializing...');
  const [streamStarted, setStreamStarted] = useState<boolean>(false);

  const handleStartStream = async () => {
    if (videoRef.current && !streamStarted) {
      setStreamStarted(true);
      await startStreaming(videoRef.current);
    }
  };

  const startStreaming = async (videoElement: HTMLVideoElement) => {
    try {
      const pc = new RTCPeerConnection();

      pc.ontrack = (event) => {
        console.log(`Video/Audio track received: ${event.track.kind}`);
        if (videoElement) {
          if (!videoElement.srcObject) {
            videoElement.srcObject = new MediaStream();
          }
          (videoElement.srcObject as MediaStream).addTrack(event.track);
        }
      };

      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const response = await fetch(`${API_HOST}/offer`, {
        method: 'POST',
        body: JSON.stringify({
          sdp: pc.localDescription?.sdp,
          type: pc.localDescription?.type,
        }),
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) throw new Error("Backend rejected WebRTC offer");

      const answer = await response.json();
      await pc.setRemoteDescription(new RTCSessionDescription(answer));
    } catch (err) {
      console.error("WebRTC error:", err);
    }
  };

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimeout: number;

    const connect = () => {
      socket = new WebSocket(`${WS_HOST}/ws`);

      socket.onopen = () => {
        setConnectionStatus('Connected');
      };

      socket.onmessage = (event) => {
        try {
          const data: FactCheck = JSON.parse(event.data);
          setFactChecks(prev => [{ ...data, id: Date.now() }, ...prev]);
        } catch (err) {
          console.error("Error parsing fact-check:", err);
        }
      };

      socket.onerror = () => {
        setConnectionStatus('Connection error');
      };

      socket.onclose = () => {
        setConnectionStatus('Disconnected');
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
      <header className="main-header">
        <div>
          <h1 className="header-title">Fact-Check Live <span className="dot-live">●</span></h1>
          <p style={{ fontWeight: 'bold', textTransform: 'uppercase', color: '#4b5563', margin: 0 }}>Real-time Stream Analysis System</p>
        </div>
        <div className="header-info">
          <div className="addr-badge">ADDR: {API_HOST}</div>
          <div className="status-text" style={{ color: connectionStatus === 'Connected' ? '#16a34a' : '#dc2626' }}>
            Status: {connectionStatus}
          </div>
        </div>
      </header>

      <main className="content-grid">
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
            <div className="waiting-overlay">Waiting for signal...</div>
          )}
        </div>

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
