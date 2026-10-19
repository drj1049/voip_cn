import React, { useState, useRef, useEffect } from 'react';
import { Headphones, Upload } from 'lucide-react';

// Telephone audio is 8000 samples per second, so every clip is converted to that
const TARGET_RATE = 8000;
const MAX_SECONDS = 30;   // longer clips are cut (the backend also enforces this)
// Same rating colours as the gauge and the metric cards
const QUALITY_COLORS = {
  EXCELLENT: '#10b981',
  GOOD: '#06b6d4',
  FAIR: '#f59e0b',
  POOR: '#f97316',
  BAD: '#ef4444'
};
// Strip colours: '0' = played fine, '1' = lost in the network, '2' = arrived too late
// (the backend sends one of these characters per 20 ms packet)
const FRAME_COLORS = { '0': '#10b981', '1': '#ef4444', '2': '#f59e0b' };

// Decode any audio file the browser understands, then turn it into a small
// mono 8 kHz 16-bit WAV (telephone quality) before sending it to the backend.
async function fileToWav(file) {
  // 1. Read the raw bytes of the chosen file
  const bytes = await file.arrayBuffer();
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  // An OfflineAudioContext is the browser's built-in audio decoder. It understands mp3, m4a,
  // wav, ogg and more, so the user can upload almost anything.
  let ctx;
  try {
    ctx = new Ctx(1, TARGET_RATE, TARGET_RATE);
  } catch (e) {
    ctx = new Ctx(1, 44100, 44100); // some browsers refuse 8 kHz contexts
  }
  // 2. Decode it into raw audio numbers
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

  // 3. Shrink to 8 kHz. For each output sample, average the group of input samples it covers
  // (averaging also acts as a simple filter that avoids harsh aliasing noise).
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

  // 4. Write a standard 16-bit WAV file: a 44 byte header (format details) followed by the samples.
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
  // Browser audio is floating point between -1 and 1; WAV wants whole numbers, so scale it up.
  // Negative and positive sides use slightly different multipliers to cover the full 16-bit range.
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return { buffer, truncated };
}

// The "Audio mode" panel. It reuses the network settings from the sliders (config), uploads a
// clip (or uses the built-in demo melody), asks the backend to run it through those conditions,
// and shows the score, two audio players and a strip showing what happened to each packet.
const AudioLab = ({ config, apiBase }) => {
  const [file, setFile] = useState(null);       // the chosen audio file (null = use the demo clip)
  const [busy, setBusy] = useState(false);       // true while the backend is working
  const [error, setError] = useState('');        // message shown in red if something fails
  const [note, setNote] = useState('');          // friendly heads-up, like "clip was cut to 30 seconds"
  const [result, setResult] = useState(null);    // the last answer from the backend
  const canvasRef = useRef(null);                // the packet strip drawing area
  const inputRef = useRef(null);                 // the hidden file picker, opened by our own button

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

  // Runs when the user presses "Apply network conditions"
  const run = async () => {
    setBusy(true);
    setError('');
    setNote('');
    try {
      // The network settings go in the URL; the audio itself goes in the request body
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

      // No file chosen = no body, and use_demo=true above tells the backend to use its own clip
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
      // On a failure the backend explains why in a "detail" field; show that message if present
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
      setBusy(false);   // always re-enable the button, whether it worked or not
    }
  };

  const m = result ? result.metrics : null;
  // With the jitter buffer off, jitter cannot be heard (see the hint shown below)
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

      {/* Tell the user why jitter will sound like nothing when no buffer is on */}
      {bufferOff && Number(config.jitter_ms) > 0 && (
        <p className="audio-hint">
          Jitter buffer is off, so jitter will not be audible. Turn it on under Advanced in the
          network conditions to hear its effect.
        </p>
      )}
      {error && <p className="audio-error">{error}</p>}
      {note && <p className="audio-hint">{note}</p>}

      {/* Everything below only appears after a successful run */}
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
              {/* The backend sends the audio as base64 text; a data: URL lets the player use it directly */}
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
