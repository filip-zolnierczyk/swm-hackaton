import React, { useEffect, useRef, useState } from 'react';
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

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimeout: number;

    const connect = () => {
      console.log("Attempting to connect to Python server...");
      socket = new WebSocket('ws://127.0.0.1:8000/ws');

      socket.onopen = () => {
        console.log("✅ WebSocket Connected!");
        setConnectionStatus('Połączono');
      };

      socket.onmessage = (event) => {
        try {
          const data: FactCheck = JSON.parse(event.data);
          const factWithId = { ...data, id: data.id || Date.now() };
          setFactChecks(prev => [factWithId, ...prev]);
        } catch (err) {
          console.error("Błąd parsowania danych:", err);
        }
      };

      socket.onerror = (error) => {
        console.error("❌ Błąd WebSocket:", error);
        setConnectionStatus('Błąd połączenia');
      };

      socket.onclose = (e) => {
        console.log(`🔌 Połączenie zamknięte. Reconnect za 2s...`);
        setConnectionStatus('Rozłączono');
        reconnectTimeout = window.setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      clearTimeout(reconnectTimeout);
    };
  }, []);

  return (
    <div className="min-h-screen w-full bg-gray-200 p-10 flex flex-col items-center font-sans overflow-x-hidden">
      
      {/* NAGŁÓWEK (SZTYWNA SZEROKOŚĆ CAŁOŚCI) */}
      <div className="w-[1700px] mb-6 flex justify-between items-end border-b-4 border-black pb-4">
        <div>
          <h1 className="text-5xl font-black uppercase text-black italic tracking-tighter">
            Fact-Check Live <span className="text-red-600">●</span>
          </h1>
          <p className="text-sm font-mono font-bold text-gray-600 uppercase">Real-time Stream Analysis System</p>
        </div>
        <div className="flex flex-col items-end">
          <div className="px-4 py-1 bg-black text-white font-mono text-xs mb-1">
            ADDR: 127.0.0.1:8000
          </div>
          <div className={`font-black uppercase text-sm ${connectionStatus === 'Połączono' ? 'text-green-600' : 'text-red-600'}`}>
            Status: {connectionStatus}
          </div>
        </div>
      </div>

      {/* GŁÓWNY KONTENER (SZTYWNE WYMIARY 1280 + 400 + GAP) */}
      <div className="flex flex-row gap-5" style={{ width: '1700px', height: '720px' }}>
        
        {/* LEWA: WIDEO*/}
        <div 
          className="bg-black border-[4px] border-black shadow-[10px_10px_0px_0px_rgba(0,0,0,1)] overflow-hidden relative"
          style={{ width: '800px', height: '600px' }}
        >
          <video 
            ref={videoRef} 
            autoPlay 
            playsInline 
            className="w-full h-full object-cover" 
          />
          {connectionStatus !== 'Połączono' && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm text-white font-black text-2xl uppercase italic">
              Oczekiwanie na sygnał...
            </div>
          )}
        </div>

        {/* PRAWA: PANEL KAFELKÓW (300 x 720 px) */}
        <div 
          className="flex flex-col gap-4 overflow-y-auto p-5 bg-white border-[4px] border-black shadow-[10px_10px_0px_0px_rgba(0,0,0,1)] custom-scrollbar"
          style={{ width: '320px', height: '720px' }}
        >
          {factChecks.length === 0 ? (
            <div className="h-full flex items-center justify-center text-black font-black uppercase italic opacity-10 text-center text-2xl leading-none">
              No Data<br/>Detected
            </div>
          ) : (
            factChecks.map((item) => (
              <div 
                key={item.id} 
                className={`p-5 border-[4px] border-black shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] flex-shrink-0 transition-transform hover:-translate-y-1
                  ${item.status === 'true' ? 'bg-green-400' : item.status === 'false' ? 'bg-red-500' : 'bg-yellow-300'}`}
              >
                <div className="border-b-4 border-black mb-3 pb-1 flex justify-between items-center">
                  <span className="font-black text-sm uppercase italic">
                    {item.status === 'true' ? '✓ Prawda' : item.status === 'false' ? '✗ Fałsz' : '⚠ Niejasne'}
                  </span>
                  <span className="text-[10px] font-bold font-mono opacity-60">LIVE</span>
                </div>
                <p className="font-black text-lg leading-tight mb-3 uppercase italic">
                  "{item.quote}"
                </p>
                <div className="bg-black/10 p-2 border-2 border-black/20">
                    <p className="text-xs font-bold leading-tight uppercase">
                        {item.analysis}
                    </p>
                </div>
              </div>
            ))
          )}
        </div>

      </div>

      {/* FOOTER */}
      <div className="w-[1700px] mt-6 text-xs font-bold text-gray-500 uppercase tracking-widest text-center">
        Engine: Python AI / WebRTC Stream / React Interface
      </div>
    </div>
  );
};

export default App;