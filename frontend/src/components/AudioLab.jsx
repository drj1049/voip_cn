import React, { useState, useRef, useEffect } from 'react';
import { Headphones, Upload } from 'lucide-react';

const TARGET_RATE = 8000;
const MAX_SECONDS = 30;
const QUALITY_COLORS = {
  EXCELLENT: '#10b981',
  GOOD: '#06b6d4',
  FAIR: '#f59e0b',
  POOR: '#f97316',
  BAD: '#ef4444'
};
const FRAME_COLORS = { '0': '#10b981', '1': '#ef4444', '2': '#f59e0b' };

// Decode any audio file the browser understands, then turn it into a small
// mono 8 kHz 16-bit WAV (telephone quality) before sending it to the backend.
async function fileToWav(file) {
  const bytes = await file.arrayBuffer();
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  let ctx;
  try {
    ctx = new Ctx(1, TARGET_RATE, TARGET_RATE);
  } catch (e) {
    ctx = new Ctx(1, 44100, 44100); // some browsers refuse 8 kHz contexts
  }
  const decoded = await ctx.decodeAudioData(bytes);

  // Mix down to mono and keep the first MAX_SECONDS only
  const rate = decoded.sampleRate;
  const truncated = decoded.length > Math.floor(rate * MAX_SECONDS);
  const length = Math.min(decoded.length, Math.floor(rate * MAX_SECONDS));
  const mono = new Float32Array(length);
  for (let c = 0; c < decoded.numberOfChannels; c++) {
    const ch = decoded.getChannelData(c);
    for (let i = 0; i < length; i++) mono[i] += ch[i] / decoded.numberOfChannels;
  }

  // Resample to 8 kHz by averaging each output sample's input window
  let samples = mono;
  if (rate !== TARGET_RATE) {
    const ratio = rate / TARGET_RATE;
    const outLen = Math.floor(length / ratio);
    samples = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
      let sum = 0;
      for (let j = start; j < end && j < length; j++) sum += mono[j];
      samples[i] = sum / (end - start);
    }
  }

  // Write a 16-bit PCM WAV
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);           // PCM
  view.setUint16(22, 1, true);           // mono
  view.setUint32(24, TARGET_RATE, true);
  view.setUint32(28, TARGET_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return { buffer, truncated };
}

const AudioLab = ({ config, apiBase }) => {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [result, setResult] = useState(null);
  const canvasRef = useRef(null);
  const inputRef = useRef(null);

  // Draw one coloured slice per 20 ms packet: played, lost or discarded as late
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !result) return;
    const ctx = canvas.getContext('2d');
    const frames = result.frames;
    const w = canvas.width;
    ctx.clearRect(0, 0, w, canvas.height);
    for (let i = 0; i < frames.length; i++) {
      ctx.fillStyle = FRAME_COLORS[frames[i]] || '#64748b';
      const x0 = Math.floor((i * w) / frames.length);
      const x1 = Math.floor(((i + 1) * w) / frames.length);
      ctx.fillRect(x0, 0, Math.max(1, x1 - x0), canvas.height);
    }
  }, [result]);

  const run = async () => {
    setBusy(true);
    setError('');
    setNote('');
    try {
      const mode = config.buffer_mode || 'off';
      const params = new URLSearchParams({
        use_demo: file ? 'false' : 'true',
        delay_ms: config.delay_ms,
        jitter_ms: config.jitter_ms,
        packet_loss_pct: config.packet_loss_pct,
        loss_mode: config.loss_mode || 'random',
        burst_length: config.burst_length ?? 5,
        buffer_mode: mode,
        buffer_ms: config.buffer_ms ?? 40
      });

      let body;
      let headers = {};
      if (file) {
        const wav = await fileToWav(file);
        body = wav.buffer;
        headers = { 'Content-Type': 'audio/wav' };
        if (wav.truncated) setNote('Clip is longer than 30 seconds, so only the first 30 seconds were used.');
      }

      const res = await fetch(`${apiBase}/audio/process?${params.toString()}`, {
        method: 'POST',
        headers,
        body
      });
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
          const j = await res.json();
          if (j.detail) detail = typeof j.detail === 'string' ? j.detail : detail;
        } catch (e) { /* keep default message */ }
        throw new Error(detail);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err.message || 'Could not process the audio');
    } finally {
      setBusy(false);
    }
  };

  const m = result ? result.metrics : null;
  const bufferOff = (config.buffer_mode || 'off') === 'off';
  const color = m ? QUALITY_COLORS[m.quality] || 'var(--accent-emerald)' : 'inherit';

  return (
    <div className="card-panel audio-lab">
      <div className="card-title">
        <span>Audio mode</span>
        <Headphones size={16} color="var(--accent-blue)" />
      </div>

      <p className="audio-intro">
        Cut a clip into 20 ms packets, send them through the network conditions set above,
        and listen to what the receiver would play. Lost packets and packets the jitter buffer
        discards as late become silence.
      </p>

      <div className="audio-controls">
        <div className="audio-source">
          <input
            ref={inputRef}
            type="file"
            accept="audio/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null);
              setResult(null);
            }}
          />
          <button className="btn btn-secondary" onClick={() => inputRef.current.click()}>
            <Upload size={15} /> {file ? 'Change audio file' : 'Upload audio file'}
          </button>
          <span className="audio-file-name">
            {file ? file.name : 'Using the built-in demo melody'}
          </span>
          {file && (
            <button
              className="audio-link"
              onClick={() => {
                setFile(null);
                setResult(null);
                if (inputRef.current) inputRef.current.value = '';
              }}
            >
              Use demo clip
            </button>
          )}
        </div>
        <button className="btn btn-primary audio-run" onClick={run} disabled={busy}>
          {busy ? 'Processing...' : 'Apply network conditions'}
        </button>
      </div>

      {bufferOff && Number(config.jitter_ms) > 0 && (
        <p className="audio-hint">
          Jitter buffer is off, so jitter will not be audible. Turn it on under Advanced in the
          network conditions to hear its effect.
        </p>
      )}
      {error && <p className="audio-error">{error}</p>}
      {note && <p className="audio-hint">{note}</p>}

      {result && (
        <div className="audio-results">
          <div className="audio-score">
            <div className="audio-mos" style={{ color }}>
              {m.mos.toFixed(2)}
              <span> / 5.0</span>
            </div>
            <div className="audio-quality" style={{ color }}>
              {m.quality.charAt(0) + m.quality.slice(1).toLowerCase()}
            </div>
            <div className="audio-stats">
              {m.packets_sent} packets · {m.packets_lost} lost · {m.packets_late} late
            </div>
            <div className="audio-stats">
              Jitter {m.jitter.toFixed(1)} ms · Latency {m.latency_avg.toFixed(0)} ms
            </div>
          </div>

          <div className="audio-players">
            <div className="audio-player">
              <label>Original</label>
              <audio controls src={`data:audio/wav;base64,${result.original_wav}`} />
            </div>
            <div className="audio-player">
              <label>After the network</label>
              <audio controls src={`data:audio/wav;base64,${result.damaged_wav}`} />
            </div>
          </div>

          <div className="audio-strip-wrap">
            <canvas ref={canvasRef} width={800} height={22} className="audio-strip" />
            <div className="audio-legend">
              <span><i style={{ background: FRAME_COLORS['0'] }} /> played</span>
              <span><i style={{ background: FRAME_COLORS['1'] }} /> lost</span>
              <span><i style={{ background: FRAME_COLORS['2'] }} /> late, discarded</span>
              <span className="audio-legend-note">Each slice is one 20 ms packet, in order</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AudioLab;
