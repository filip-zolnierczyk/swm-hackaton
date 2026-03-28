import React, { useEffect, useRef, useState } from 'react';
import './index.css';

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

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimeout: number;

    const connect = () => {
      socket = new WebSocket('ws://127.0.0.1:8000/ws');
      socket.onopen = () => setConnectionStatus('Połączono');
      socket.onmessage = (event) => {
        try {
          const data: FactCheck = JSON.parse(event.data);
          setFactChecks(prev => [{ ...data, id: Date.now() }, ...prev]);
        } catch (err) { console.error(err); }
      };
      socket.onerror = () => setConnectionStatus('Błąd połączenia');
      socket.onclose = () => {
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
      
      <header className="main-header">
        <div>
          <h1 className="header-title">Fact-Check Live <span className="dot-live">●</span></h1>
          <p style={{ fontWeight: 'bold', textTransform: 'uppercase', color: '#4b5563', margin: 0 }}>Real-time Stream Analysis System</p>
        </div>
        <div className="header-info">
          <div className="addr-badge">ADDR: 127.0.0.1:8000</div>
          <div className="status-text" style={{ color: connectionStatus === 'Połączono' ? '#16a34a' : '#dc2626' }}>
            Status: {connectionStatus}
          </div>
        </div>
      </header>

      <main className="content-grid">
        
        <div className="video-box">
          <video ref={videoRef} autoPlay playsInline />
          {connectionStatus !== 'Połączono' && (
            <div className="waiting-overlay">Oczekiwanie na sygnał...</div>
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
                    {item.status === 'true' ? '✓ Prawda' : item.status === 'false' ? '✗ Fałsz' : '⚠ Niejasne'}
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