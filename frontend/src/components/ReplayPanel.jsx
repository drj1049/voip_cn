import React, { useState, useEffect, useRef } from 'react';
import { Radio, Upload, Play, ArrowLeft } from 'lucide-react';

// "Real call replay": instead of the synthetic packet generator, the analyzer reads the packets
// of a REAL call that was recorded with Wireshark or tcpdump (a .pcap / .pcapng file) and runs
// them through the same jitter, loss and MOS code. This panel picks the recording and starts it.

const SPEEDS = [1, 2, 5, 10];

// 125 seconds -> "2:05"
const fmtTime = (s) => {
  const t = Math.max(0, Math.round(Number(s) || 0));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
};
// 5520 -> "5,520"
const fmtInt = (n) => (n === undefined || n === null ? '-' : Number(n).toLocaleString());
const fmtKB = (bytes) =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

const ReplayPanel = ({ apiBase, metrics, onModeChanged }) => {
  const [captures, setCaptures] = useState([]);     // capture files the backend knows about
  const [selected, setSelected] = useState('');     // the file chosen in the dropdown
  const [streams, setStreams] = useState([]);       // RTP streams found inside the chosen file
  const [ssrc, setSsrc] = useState('');             // which stream to replay ('' = the voice stream)
  const [baseDelay, setBaseDelay] = useState('40'); // assumed one-way delay of the fastest packet (text, so it can be edited freely)
  const [speed, setSpeed] = useState(1);            // 1 = real time
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  const isReplay = metrics.source === 'replay';
  const state = metrics.replay_state;

  // Small helper: call the backend and turn an error response into a readable message
  const call = async (path, options) => {
    const res = await fetch(`${apiBase}${path}`, options);
    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try {
        const j = await res.json();
        if (j.detail && typeof j.detail === 'string') detail = j.detail;
      } catch (e) { /* keep the default message */ }
      throw new Error(detail);
    }
    return res.json();
  };

  // Look inside the chosen file and list its streams
  const choose = async (name) => {
    setSelected(name);
    setStreams([]);
    setSsrc('');
    if (!name) return;
    try {
      const data = await call(`/replay/streams?capture=${encodeURIComponent(name)}`);
      setStreams(data.streams);
      setError('');
    } catch (e) {
      setError(e.message);
    }
  };

  const refreshCaptures = async (pick) => {
    try {
      const data = await call('/replay/captures');
      setCaptures(data.captures);
      const wanted = pick || selected || data.loaded || (data.captures[0] && data.captures[0].name) || '';
      if (wanted && wanted !== selected) await choose(wanted);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refreshCaptures();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const data = await call(`/replay/upload?name=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file
      });
      await refreshCaptures(data.name);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const clampDelay = () => {
    const n = Math.max(0, Math.min(500, Number(baseDelay) || 0));
    setBaseDelay(String(n));
    return n;
  };

  const start = async () => {
    if (!selected) return;
    setBusy(true);
    setError('');
    try {
      const params = new URLSearchParams({ capture: selected, base_delay_ms: clampDelay(), speed });
      if (ssrc) params.set('ssrc', ssrc);
      await call(`/replay/start?${params.toString()}`, { method: 'POST' });
      onModeChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const backToSimulator = async () => {
    setBusy(true);
    try {
      await call('/simulation/start', { method: 'POST' });
      onModeChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---- what to show on the right-hand side ----------------------------------------------

  const info = metrics.stream || {};
  const progressPct = Math.round((metrics.progress || 0) * 100);

  // Before a replay starts, preview the stream that would be replayed (the chosen one, or the voice stream)
  const preview = ssrc
    ? streams.find((s) => String(s.ssrc_int) === String(ssrc))
    : streams.find((s) => s.looks_like_audio) || streams[0];

  const facts = isReplay
    ? [
        ['Packets', fmtInt(info.packets_in_capture)],
        ['Duration', fmtTime(info.duration_s)],
        ['Clock rate', info.clock_rate ? `${info.clock_rate / 1000} kHz` : '-'],
        ['Missing', fmtInt(info.packets_missing_in_capture)],
        ['Reordered', fmtInt(info.reordered_arrivals)],
        ['Duplicates', fmtInt(info.duplicates_removed)]
      ]
    : preview
    ? [
        ['Packets', fmtInt(preview.packets)],
        ['Duration', fmtTime(preview.duration_s)],
        ['Clock rate', `${preview.clock_rate / 1000} kHz`],
        ['Rate', `${preview.packets_per_second} pkt/s`]
      ]
    : [];

  const pill = !isReplay
    ? { cls: 'sim', text: 'Live simulator' }
    : state === 'playing'
    ? { cls: 'playing', text: 'Replaying' }
    : state === 'finished'
    ? { cls: 'finished', text: 'Finished' }
    : { cls: 'stopped', text: 'Stopped' };

  return (
    <div className="card-panel replay-panel">
      <div className="card-title">
        <span className="replay-title"><Radio size={16} color="var(--accent-blue)" /> Real call replay</span>
        <span className={`replay-pill ${pill.cls}`}><i />{pill.text}</span>
      </div>
      <p className="replay-lead">
        Analyse packets recorded from a real call instead of simulated ones. Jitter, packet loss and call
        quality are measured from the recording.
      </p>

      <div className="replay-grid">
        {/* Left: choose the recording and how to play it */}
        <div className="replay-setup">
          <div className="replay-field">
            <label htmlFor="replay-capture">Capture file</label>
            <div className="replay-file-row">
              <select
                id="replay-capture"
                value={selected}
                onChange={(e) => choose(e.target.value)}
                className="replay-input"
                disabled={captures.length === 0}
              >
                {captures.length === 0 && <option value="">No captures yet</option>}
                {captures.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} ({fmtKB(c.size_bytes)})
                  </option>
                ))}
              </select>
              <input
                ref={inputRef}
                type="file"
                accept=".pcap,.pcapng,.cap"
                style={{ display: 'none' }}
                onChange={(e) => upload(e.target.files && e.target.files[0])}
              />
              <button
                className="btn btn-secondary replay-upload"
                onClick={() => inputRef.current && inputRef.current.click()}
                disabled={busy}
                title="Upload a .pcap or .pcapng file (40 MB maximum)"
              >
                <Upload size={14} /> Upload
              </button>
            </div>
            <span className="replay-hint">
              Recorded with Wireshark or tcpdump. Files over 40 MB can be placed in the captures folder instead.
            </span>
          </div>

          {streams.length > 1 && (
            <div className="replay-field">
              <label htmlFor="replay-stream">RTP stream</label>
              <select id="replay-stream" value={ssrc} onChange={(e) => setSsrc(e.target.value)} className="replay-input">
                <option value="">Voice stream (automatic)</option>
                {streams.map((s) => (
                  <option key={s.ssrc} value={s.ssrc_int}>
                    {s.ssrc} · {fmtInt(s.packets)} packets · {s.clock_rate / 1000} kHz{s.looks_like_audio ? ' · audio' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="replay-row">
            <div className="replay-field">
              <label htmlFor="replay-delay">Assumed base delay</label>
              <div className="replay-number">
                <input
                  id="replay-delay"
                  type="number"
                  min="0"
                  max="500"
                  value={baseDelay}
                  onChange={(e) => setBaseDelay(e.target.value)}
                  onBlur={clampDelay}
                  className="replay-input"
                />
                <em>ms</em>
              </div>
            </div>
            <div className="replay-field">
              <label>Speed</label>
              <div className="segmented">
                {SPEEDS.map((v) => (
                  <button key={v} className={`seg-btn ${speed === v ? 'active' : ''}`} onClick={() => setSpeed(v)}>
                    {v}x
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="replay-actions">
            <button className="btn btn-primary" onClick={start} disabled={busy || !selected}>
              <Play size={15} /> {isReplay ? 'Load and replay' : 'Replay call'}
            </button>
            {isReplay && (
              <button className="btn btn-secondary" onClick={backToSimulator} disabled={busy}>
                <ArrowLeft size={15} /> Back to simulator
              </button>
            )}
          </div>

          {error && <p className="replay-error">{error}</p>}
        </div>

        {/* Right: what is loaded, and how far the replay has got */}
        <div className="replay-session">
          {isReplay ? (
            <>
              <div className="replay-session-head">
                <span className="replay-session-name">{metrics.capture}</span>
                <span className="replay-session-sub">Stream {info.ssrc}</span>
              </div>
              <div className="replay-progress">
                <div className="replay-bar">
                  <div className="replay-bar-fill" style={{ width: `${progressPct}%` }} />
                </div>
                <div className="replay-time">
                  <span>{fmtTime(metrics.position_s)}</span>
                  <span>{progressPct}%</span>
                  <span>{fmtTime(metrics.duration_s)}</span>
                </div>
              </div>
            </>
          ) : preview ? (
            <div className="replay-session-head">
              <span className="replay-session-name">{selected}</span>
              <span className="replay-session-sub">
                {ssrc ? 'Selected stream' : 'Voice stream detected'} · {preview.ssrc}
              </span>
            </div>
          ) : (
            <div className="replay-empty">
              <Radio size={22} />
              <strong>No call loaded</strong>
              <span>Pick a recording and press Replay call.</span>
            </div>
          )}

          {facts.length > 0 && (
            <div className="replay-facts">
              {facts.map(([label, value]) => (
                <div className="replay-fact" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <details className="replay-help">
        <summary>How these numbers are measured</summary>
        <ul>
          <li><strong>Jitter</strong> is RFC 3550 jitter, worked out from the real arrival times and RTP timestamps.</li>
          <li><strong>Packet loss</strong> comes from gaps in the real sequence numbers. Duplicates are removed and reordering is handled.</li>
          <li>
            <strong>Delay</strong> cannot be measured from a single capture, so the fastest packet is assumed to
            take {isReplay ? info.assumed_base_delay_ms : baseDelay || 0} ms. Every other packet gets that plus the extra delay it really had.
          </li>
          <li><strong>The sliders above</strong> add extra delay, jitter and loss on top of the recording. Keep them at zero to see the call as it was.</li>
        </ul>
      </details>
    </div>
  );
};

export default ReplayPanel;
