import React, { useState, useEffect, useRef } from 'react';
import { Activity, Waves, ShieldAlert, Award, PhoneCall } from 'lucide-react';

import ControlPanel from './ControlPanel';
import MosGauge from './MosGauge';
import MetricCard from './MetricCard';
import LatencyChart from './LatencyChart';
import JitterChart from './JitterChart';
import PacketLossCard from './PacketLossCard';

const API_BASE = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';

const Dashboard = () => {
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

  const [config, setConfig] = useState({
    delay_ms: 20,
    jitter_ms: 2,
    packet_loss_pct: 0
  });

  const [history, setHistory] = useState([]);
  const wsRef = useRef(null);

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
    const connectWs = () => {
      const socket = new WebSocket(WS_URL);
      wsRef.current = socket;

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
        // Auto-reconnect every 2 seconds
        setTimeout(connectWs, 2000);
      };

      socket.onerror = (err) => {
        socket.close();
      };
    };

    connectWs();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Update Config handler
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

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-title-box">
          <h1>
            <PhoneCall size={26} color="var(--accent-blue)" />
            Real-Time VoIP Call Quality Analyzer
          </h1>
          <p>Computer Networks Project — Review 2 Network Simulation & QoS Monitoring</p>
        </div>
        <div className={`status-badge ${!isRunning ? 'stopped' : ''}`}>
          <div className="status-dot"></div>
          <span>{isRunning ? '● Simulation Running' : '● Simulation Stopped'}</span>
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

      {/* 4 KPI Metric Cards */}
      <div className="metric-cards-grid">
        <MetricCard
          title="LATENCY"
          value={metrics.latency ? metrics.latency.toFixed(1) : '0.0'}
          unit="ms"
          subValue={`Average: ${metrics.latency_avg ? metrics.latency_avg.toFixed(1) : '0.0'} ms (Min: ${metrics.latency_min ? metrics.latency_min.toFixed(1) : '0'} / Max: ${metrics.latency_max ? metrics.latency_max.toFixed(1) : '0'})`}
          color="var(--accent-blue)"
          icon={Activity}
        />

        <MetricCard
          title="JITTER (RFC 3550)"
          value={metrics.jitter ? metrics.jitter.toFixed(1) : '0.0'}
          unit="ms"
          subValue="Standard RFC 3550 Interarrival Deviation"
          color="var(--accent-purple)"
          icon={Waves}
        />

        <MetricCard
          title="PACKET LOSS"
          value={metrics.packet_loss ? metrics.packet_loss.toFixed(1) : '0.0'}
          unit="%"
          subValue={`${metrics.packets_lost} lost / ${metrics.packets_sent} sent`}
          color={metrics.packet_loss > 5 ? 'var(--accent-red)' : 'var(--accent-emerald)'}
          icon={ShieldAlert}
        />

        <MetricCard
          title="ESTIMATED MOS"
          value={metrics.mos ? metrics.mos.toFixed(2) : '1.00'}
          unit="/ 5.0"
          subValue={`Rating: ${metrics.quality} (ITU-T G.107 E-model)`}
          color="var(--accent-emerald)"
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
    </div>
  );
};

export default Dashboard;
