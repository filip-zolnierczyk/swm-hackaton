import React, { useEffect, useRef, useState } from 'react';
import './index.css';

interface FactCheck {
  id?: number;
  status: 'true' | 'false' | 'mixed' | 'error';
  quote: string;
  analysis: string;
  sources?: Array<{ title?: string; url?: string; text?: string; html?: string }>;
  isLoading?: boolean;
  isThorough?: boolean; // Mark thorough mode tiles
  isForced?: boolean; // Mark forced fact-checks
}

// Load config from environment variables
const API_HOST = import.meta.env.VITE_API_HOST || 'http://127.0.0.1:8000';
const WS_HOST = import.meta.env.VITE_WS_HOST || 'ws://127.0.0.1:8000';

const App: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [factChecks, setFactChecks] = useState<FactCheck[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<string>('Initializing...');
  const [streamStarted, setStreamStarted] = useState<boolean>(false);
  const [thoroughMode, setThoroughMode] = useState<boolean>(false);
  const recentClaimsRef = useRef<Map<string, number>>(new Map()); // Track recently checked claims with timestamp

  // Buffer for recent transcriptions (last ~60 seconds)
  const transcriptionBufferRef = useRef<Array<{ text: string; timestamp: number }>>([])

  const handleStartStream = async () => {
    if (videoRef.current && !streamStarted) {
      setStreamStarted(true);
      await startStreaming(videoRef.current);
    }
  };

  const handleThoroughModeToggle = (enabled: boolean) => {
    setThoroughMode(enabled);
    setFactChecks([]);
    recentClaimsRef.current.clear(); // Clear recent claims when switching modes
  };

  const fetchThoroughAnalysis = async (claim: string) => {
    const loadingId = Date.now();
    setFactChecks(prev => [{
      id: loadingId,
      status: 'mixed',
      quote: claim,
      analysis: '',
      isLoading: true,
      isThorough: true
    }, ...prev]);

    try {
      const response = await fetch(`${API_HOST}/thorough`, {
        method: 'POST',
        body: JSON.stringify({ text: claim }),
        headers: { 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const result = await response.json();
        // Handle both single object and array responses
        const results = Array.isArray(result) ? result : [result];

        setFactChecks(prev => {
          // Remove loading tile
          let updated = prev.filter(item => item.id !== loadingId);
          // Add all results
          results.forEach((res, idx) => {
            updated.unshift({
              id: loadingId + idx,
              status: res.status || 'mixed',
              quote: res.quote || claim,
              analysis: res.analysis || '',
              sources: res.sources || [],
              isLoading: false,
              isThorough: true
            });
          });
          return updated;
        });
      } else {
        // Error response - show error tile (purple)
        const errorText = response.status === 429 ? 'Rate limit exceeded - thorough check failed' : 'Thorough check failed';
        setFactChecks(prev =>
          prev.map(item =>
            item.id === loadingId
              ? { ...item, status: 'error', analysis: errorText, isLoading: false }
              : item
          )
        );
      }
    } catch (err) {
      console.error('Error fetching thorough analysis:', err);
      setFactChecks(prev =>
        prev.map(item =>
          item.id === loadingId
            ? { ...item, status: 'error', analysis: 'Error checking claim', isLoading: false }
            : item
        )
      );
    }
  };

  const addTranscriptionToBuffer = (text: string) => {
    const now = Date.now();
    const buffer = transcriptionBufferRef.current;

    // Add new transcription
    buffer.push({ text, timestamp: now });

    // Keep only last 60 seconds
    const WINDOW_MS = 60000;
    while (buffer.length > 0 && now - buffer[0].timestamp > WINDOW_MS) {
      buffer.shift();
    }
  };

  const handleForceCheck = async () => {
    const buffer = transcriptionBufferRef.current;
    if (buffer.length === 0) {
      alert('No recent transcriptions to check');
      return;
    }

    // Combine all buffer items into one text
    const combinedText = buffer.map(item => item.text).join(' ').trim();
    console.log(`Force checking (${buffer.length} transcriptions):`, combinedText.substring(0, 100));

    // Fetch with special flag
    const loadingId = Date.now();
    setFactChecks(prev => [{
      id: loadingId,
      status: 'mixed',
      quote: `[FORCED] ${combinedText.substring(0, 100)}${combinedText.length > 100 ? '...' : ''}`,
      analysis: '',
      isLoading: true,
      isThorough: true,
      isForced: true
    }, ...prev]);

    try {
      const response = await fetch(`${API_HOST}/thorough`, {
        method: 'POST',
        body: JSON.stringify({ text: combinedText }),
        headers: { 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const result = await response.json();
        const results = Array.isArray(result) ? result : [result];

        setFactChecks(prev => {
          let updated = prev.filter(item => item.id !== loadingId);
          results.forEach((res, idx) => {
            updated.unshift({
              id: loadingId + idx,
              status: res.status || 'mixed',
              quote: res.quote || combinedText.substring(0, 100),
              analysis: res.analysis || '',
              sources: res.sources || [],
              isLoading: false,
              isThorough: true,
              isForced: true
            });
          });
          return updated;
        });
      } else {
        setFactChecks(prev =>
          prev.map(item =>
            item.id === loadingId
              ? { ...item, status: 'error', analysis: 'Force check failed', isLoading: false }
              : item
          )
        );
      }
    } catch (err) {
      console.error('Error during force check:', err);
      setFactChecks(prev =>
        prev.map(item =>
          item.id === loadingId
            ? { ...item, status: 'error', analysis: 'Error during force check', isLoading: false }
            : item
        )
      );
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
          const normalizedClaim = data.quote.toLowerCase().trim();
          const now = Date.now();

          console.log('Message received. Thorough mode:', thoroughMode, 'Data:', data);

          // Buffer all incoming transcriptions for force-check
          addTranscriptionToBuffer(data.quote);

          if (!thoroughMode) {
            const newCheck = { ...data, id: Date.now() };
            setFactChecks(prev => [newCheck, ...prev]);
          } else {
            const lastCheckTime = recentClaimsRef.current.get(normalizedClaim);

            // Throttle to avoid rechecking the same transcription chunk
            const THROTTLE_MS = 2000;

            if (lastCheckTime && now - lastCheckTime < THROTTLE_MS) {
              return;
            }

            recentClaimsRef.current.set(normalizedClaim, now);

            // Send entire transcription to backend - Gemini extracts all claims via THOROUGH_SYSTEM_PROMPT
            fetchThoroughAnalysis(data.quote);
          }
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
  }, [thoroughMode]);

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
          <label className="thorough-toggle">
            <input
              type="checkbox"
              checked={thoroughMode}
              onChange={(e) => handleThoroughModeToggle(e.target.checked)}
            />
            Thorough Mode
          </label>
          <button
            className="force-check-btn"
            onClick={handleForceCheck}
            title="Force fact-check on last 60 seconds of transcriptions"
          >
            Force Check
          </button>
        </div>
      </header>

      <main className="content-grid">
        <div className="video-box">
          <video ref={videoRef} autoPlay playsInline muted={true} />
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
            factChecks
              .filter(item => item.isForced || (thoroughMode ? item.isThorough : !item.isThorough))
              .map((item) => (
              <div
                key={item.id}
                className={`fact-card card-${item.isLoading ? 'loading' : item.status}`}
              >
                <div className="card-header">
                  <span className="card-verdict">
                    {item.isLoading ? '⏳ Analyzing...' : item.status === 'true' ? '✓ True' : item.status === 'false' ? '✗ False' : item.status === 'error' ? '⚠ Error' : '⚠ Mixed'}
                  </span>
                  <span className="card-live-label">LIVE</span>
                </div>
                <p className="card-quote">"{item.quote}"</p>
                <div className="card-analysis-box">
                  <p className="card-analysis-text">
                    {item.isLoading ? 'Fetching thorough analysis with sources...' : item.analysis}
                  </p>
                </div>
                {item.sources && item.sources.length > 0 && (
                  <div className="card-sources">
                    <p className="card-sources-label">Sources:</p>
                    {item.sources.map((source, idx) => (
                      source.html ? (
                        <div
                          key={idx}
                          className="card-source-html"
                          dangerouslySetInnerHTML={{ __html: source.html }}
                        />
                      ) : source.url ? (
                        <a
                          key={idx}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="card-source-link"
                        >
                          {source.title}
                        </a>
                      ) : (
                        <p key={idx} className="card-source-text">{source.text}</p>
                      )
                    ))}
                  </div>
                )}
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
