import React, { useState, useEffect, useRef } from 'react';
import { Activity, Waves, ShieldAlert, Award, PhoneCall } from 'lucide-react';

import ControlPanel from './ControlPanel';
import MosGauge from './MosGauge';
import MetricCard from './MetricCard';
import LatencyChart from './LatencyChart';
import JitterChart from './JitterChart';
import PacketLossCard from './PacketLossCard';
import AudioLab from './AudioLab';

// When the backend serves this page (production), use the same address.
// When running "npm run dev" (port 3000), talk to the backend on port 8000.
// VITE_API_BASE and VITE_WS_URL can override both.
const isDevServer = window.location.port === '3000';
const API_BASE =
  import.meta.env.VITE_API_BASE || (isDevServer ? 'http://localhost:8000' : '');
const WS_URL =
  import.meta.env.VITE_WS_URL ||
  (isDevServer
    ? 'ws://localhost:8000/ws'
    : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`);

// The main screen. It holds all the live data in state, listens to the backend over a WebSocket,
// and hands the numbers down to the smaller components (gauge, cards, charts, audio panel).
const Dashboard = () => {
  // Latest numbers from the backend. These starting values are shown until the first update arrives.
  const [metrics, setMetrics] = useState({
    timestamp: Date.now(),
    status: 'STOPPED',
    latency: 0,
    latency_avg: 0,
    latency_min: 0,
    latency_max: 0,
    jitter: 0,
    packet_loss: 0,
    packets_sent: 0,
    packets_received: 0,
    packets_lost: 0,
    mos: 4.5,
    r_factor: 93.2,
    quality: 'EXCELLENT'
  });

  // The slider settings currently chosen by the user
  const [config, setConfig] = useState({
    delay_ms: 20,
    jitter_ms: 2,
    packet_loss_pct: 0,
    loss_mode: 'random',
    burst_length: 5,
    buffer_mode: 'off',
    buffer_ms: 40
  });

  const [history, setHistory] = useState([]);       // recent readings, used by the graphs
  const [connected, setConnected] = useState(false); // is the WebSocket to the backend open?
  const wsRef = useRef(null);                        // keeps the socket so we can close it later

  // Runs once when the page opens: load the current settings, then open the live data stream.
  // Initialize WebSocket telemetry stream & fetch current config
  useEffect(() => {
    // Fetch initial config
    fetch(`${API_BASE}/config`)
      .then(res => res.json())
      .then(data => {
        if (data) setConfig(data);
      })
      .catch(err => console.log('Config fetch note:', err.message));

    // Connect WebSocket
    // "disposed" is set when the page closes, so we stop trying to reconnect after that
    let disposed = false;
    let reconnectTimer = null;

    const connectWs = () => {
      const socket = new WebSocket(WS_URL);
      wsRef.current = socket;

      socket.onopen = () => setConnected(true);

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMetrics(data);

          // Append formatted timestamped point for rolling Recharts graphs (max 50 points)
          const timeStr = new Date(data.timestamp * 1000).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          });

          const newPoint = {
            time: timeStr,
            latency: data.latency,
            jitter: data.jitter,
            packet_loss: data.packet_loss,
            mos: data.mos
          };

          setHistory(prev => {
            const updated = [...prev, newPoint];
            return updated.slice(-45); // Keep rolling 45 data points
          });
        } catch (e) {
          console.error('Error parsing WebSocket telemetry:', e);
        }
      };

      socket.onclose = () => {
        setConnected(false);
        // Auto-reconnect every 2 seconds
        if (!disposed) reconnectTimer = setTimeout(connectWs, 2000);
      };

      socket.onerror = (err) => {
        socket.close();   // closing triggers onclose above, which schedules a reconnect
      };
    };

    connectWs();

    // Cleanup when leaving the page: stop reconnecting and close the socket
    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Update Config handler
  // Updates the screen straight away, then tells the backend, so sliders feel instant.
  const handleConfigChange = async (newConfig) => {
    setConfig(newConfig);
    try {
      await fetch(`${API_BASE}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig)
      });
    } catch (err) {
      console.error('Failed to update config:', err);
    }
  };

  // Start Simulation handler
  const handleStart = async () => {
    try {
      await fetch(`${API_BASE}/simulation/start`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to start simulation:', err);
    }
  };

  // Stop Simulation handler
  const handleStop = async () => {
    try {
      await fetch(`${API_BASE}/simulation/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop simulation:', err);
    }
  };

  // Reset Simulation handler
  const handleReset = async () => {
    setHistory([]);
    try {
      await fetch(`${API_BASE}/simulation/reset`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to reset simulation:', err);
    }
  };

  const isRunning = metrics.status === 'RUNNING';

  // Display helpers
  // fmt: show a number with one decimal (and 0.0 for missing values)
  const fmt = (v) => (v ? Number(v).toFixed(1) : '0.0');
  // With a jitter buffer on, the cards show buffer details instead of the plain RFC 3550 label
  const bufferOn = metrics.buffer_mode && metrics.buffer_mode !== 'off';
  const qualityLabel = metrics.quality
    ? metrics.quality.charAt(0) + metrics.quality.slice(1).toLowerCase()
    : '';
  // Colour for each rating, the same ones used by the gauge and the CSS badges
  const QUALITY_COLORS = {
    EXCELLENT: '#10b981',
    GOOD: '#06b6d4',
    FAIR: '#f59e0b',
    POOR: '#f97316',
    BAD: '#ef4444'
  };
  const qualityColor = QUALITY_COLORS[metrics.quality] || 'var(--accent-emerald)';

  return (
    <div className="app-container">
      {/* Page layout from top to bottom: header, controls + gauge, four metric cards,
          two charts, packet loss card, audio mode, footer */}
      {/* Header */}
      <header className="app-header">
        <div className="header-title-box">
          <h1>
            <PhoneCall size={26} color="var(--accent-blue)" />
            Real-Time VoIP Call Quality Analyzer
          </h1>
          <p>Simulate network problems and watch estimated call quality respond in real time</p>
        </div>
        <div className={`status-badge ${!isRunning || !connected ? 'stopped' : ''}`}>
          <div className="status-dot"></div>
          <span>
            {!connected ? 'Backend offline' : isRunning ? 'Simulation running' : 'Simulation stopped'}
          </span>
        </div>
      </header>

      {/* Top Grid: Controls + MOS Gauge */}
      <div className="top-section-grid">
        <ControlPanel
          config={config}
          onConfigChange={handleConfigChange}
          isRunning={isRunning}
          onStart={handleStart}
          onStop={handleStop}
          onReset={handleReset}
        />
        <MosGauge
          mos={metrics.mos}
          quality={metrics.quality}
          rFactor={metrics.r_factor}
        />
      </div>

      {/* Key metrics */}
      <div className="metric-cards-grid">
        <MetricCard
          title="Latency"
          value={fmt(metrics.latency)}
          unit="ms"
          subValue={`Average ${fmt(metrics.latency_avg)} ms · Max ${fmt(metrics.latency_max)} ms`}
          color="var(--accent-blue)"
          icon={Activity}
        />

        <MetricCard
          title="Jitter"
          value={fmt(metrics.jitter)}
          unit="ms"
          subValue={
            bufferOn
              ? `${metrics.buffer_mode} buffer ${Number(metrics.buffer_ms).toFixed(0)} ms · ${Number(metrics.late_pct).toFixed(1)}% late`
              : 'RFC 3550 interarrival jitter'
          }
          color="var(--accent-purple)"
          icon={Waves}
        />

        <MetricCard
          title="Packet loss"
          value={fmt(metrics.packet_loss)}
          unit="%"
          subValue={`${metrics.packets_lost} of ${metrics.packets_sent} packets${metrics.burst_ratio > 1.2 ? ' · bursty' : ''}`}
          color={metrics.packet_loss > 5 ? 'var(--accent-red)' : 'var(--accent-emerald)'}
          icon={ShieldAlert}
        />

        <MetricCard
          title="Estimated MOS"
          value={metrics.mos ? metrics.mos.toFixed(2) : '1.00'}
          unit="/ 5.0"
          subValue={
            bufferOn
              ? `${qualityLabel} · playout delay ${Number(metrics.playout_delay).toFixed(0)} ms`
              : `${qualityLabel} · ITU-T G.107`
          }
          color={qualityColor}
          icon={Award}
        />
      </div>

      {/* Live Recharts Graphs */}
      <div className="charts-grid">
        <LatencyChart data={history} />
        <JitterChart data={history} />
      </div>

      {/* Packet Loss Details Card */}
      <PacketLossCard
        data={history}
        packetsSent={metrics.packets_sent}
        packetsReceived={metrics.packets_received}
        packetsLost={metrics.packets_lost}
        lossPct={metrics.packet_loss}
      />

      {/* Audio mode: run a real clip through the same network conditions */}
      <AudioLab config={config} apiBase={API_BASE} />

      <footer className="app-footer">
        Synthetic RTP-style traffic over local UDP. Jitter follows RFC 3550 and quality
        scores use a simplified ITU-T G.107 E-model.
      </footer>
    </div>
  );
};

export default Dashboard;
