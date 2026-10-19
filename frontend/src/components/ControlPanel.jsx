import React from 'react';
import { Play, Square, RotateCcw, Sliders, Sparkles } from 'lucide-react';

// The quick scenario buttons. Each one just sets delay, jitter and loss to a ready-made combination.
const SCENARIOS = [
  { name: 'Good network', delay: 20, jitter: 2, loss: 0 },
  { name: 'High latency', delay: 200, jitter: 5, loss: 0 },
  { name: 'High jitter', delay: 50, jitter: 60, loss: 0 },
  { name: 'Packet loss', delay: 50, jitter: 10, loss: 10 },
  { name: 'Poor network', delay: 250, jitter: 80, loss: 15 }
];

// The "Network conditions" box: scenario buttons, the three sliders, the Advanced section
// and the Start/Stop/Reset buttons. It does not talk to the server itself. It calls
// onConfigChange with the new settings, and Dashboard.jsx sends them to the backend.
const ControlPanel = ({
  config,
  onConfigChange,
  isRunning,
  onStart,
  onStop,
  onReset
}) => {
  // Change one setting and keep all the others as they were ({ ...config } copies the old ones)
  const setField = (field, value) => {
    onConfigChange({ ...config, [field]: value });
  };

  // Slider values arrive as text, so turn them into real numbers before saving
  const handleSliderChange = (field, value) => {
    setField(field, parseFloat(value));
  };

  // Scenarios only change delay, jitter and loss. The advanced settings
  // (loss pattern, jitter buffer) stay as the user left them.
  const applyScenario = (s) => {
    onConfigChange({
      ...config,
      delay_ms: s.delay,
      jitter_ms: s.jitter,
      packet_loss_pct: s.loss
    });
  };

  // A scenario button is highlighted when the sliders currently match it exactly
  const isActive = (s) =>
    config.delay_ms === s.delay &&
    config.jitter_ms === s.jitter &&
    config.packet_loss_pct === s.loss;

  // Fall back to sensible defaults in case the backend has not sent these settings yet
  const lossMode = config.loss_mode === 'burst' ? 'burst' : 'random';
  const bufferMode = config.buffer_mode || 'off';

  // The short grey text next to "Advanced", so the current choices are visible even when it is collapsed
  const advancedSummary = [
    lossMode === 'burst' ? `Bursty loss (${config.burst_length} packets)` : 'Random loss',
    bufferMode === 'fixed'
      ? `Fixed buffer ${config.buffer_ms} ms`
      : bufferMode === 'adaptive'
      ? 'Adaptive buffer'
      : 'No buffer'
  ].join(' · ');

  // Helpers that return markup (not components), so sliders keep focus while dragging
  // (If these were components, React would rebuild them on every move and drop the drag.)
  const renderSlider = (label, field, unit, min, max, step) => (
    <div className="slider-item">
      <label>
        <span>{label}</span>
        <span className="val">
          {config[field]}
          {unit}
        </span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={config[field]}
        onChange={(e) => handleSliderChange(field, e.target.value)}
        className="custom-slider"
      />
    </div>
  );

  // A row of toggle buttons where exactly one option is selected, like Random / Bursty
  const renderChoice = (field, current, options) => (
    <div className="segmented">
      {options.map((o) => (
        <button
          key={o.value}
          className={`seg-btn ${current === o.value ? 'active' : ''}`}
          onClick={() => setField(field, o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="card-panel">
      <div className="card-title">
        <span>Network conditions</span>
        <Sliders size={16} color="var(--accent-blue)" />
      </div>

      {/* Quick scenarios */}
      <div className="presets-container first">
        <div className="presets-title">
          <Sparkles size={13} color="var(--accent-amber)" />
          <span>Quick scenarios</span>
        </div>
        <div className="preset-buttons-grid">
          {SCENARIOS.map((s) => (
            <button
              key={s.name}
              className={`preset-btn ${isActive(s) ? 'active' : ''}`}
              title={`${s.delay} ms delay, ${s.jitter} ms jitter, ${s.loss}% loss`}
              onClick={() => applyScenario(s)}
            >
              {s.name}
            </button>
          ))}
        </div>
      </div>

      {/* Main sliders */}
      <div className="sliders-group">
        {renderSlider('Delay', 'delay_ms', ' ms', 0, 500, 5)}
        {renderSlider('Jitter', 'jitter_ms', ' ms', 0, 100, 1)}
        {renderSlider('Packet loss', 'packet_loss_pct', '%', 0, 30, 0.5)}
      </div>

      {/* Advanced settings, collapsed by default. <details> is built into HTML, no code needed to open it. */}
      <details className="advanced">
        <summary>
          <span>Advanced</span>
          <span className="advanced-summary">{advancedSummary}</span>
        </summary>
        <div className="advanced-body">
          <div className="slider-item">
            <label>
              <span>Loss pattern</span>
            </label>
            {renderChoice('loss_mode', lossMode, [
              { value: 'random', label: 'Random' },
              { value: 'burst', label: 'Bursty' }
            ])}
          </div>

          {/* The burst length slider only makes sense for bursty loss, so hide it otherwise */}
          {lossMode === 'burst' &&
            renderSlider('Average burst length', 'burst_length', ' packets', 1, 20, 1)}

          <div className="slider-item">
            <label>
              <span>Jitter buffer</span>
            </label>
            {renderChoice('buffer_mode', bufferMode, [
              { value: 'off', label: 'Off' },
              { value: 'fixed', label: 'Fixed' },
              { value: 'adaptive', label: 'Adaptive' }
            ])}
          </div>

          {/* Depth only matters in Fixed mode (Adaptive picks its own depth from the jitter) */}
          {bufferMode === 'fixed' &&
            renderSlider('Buffer depth', 'buffer_ms', ' ms', 0, 200, 5)}
        </div>
      </details>

      {/* Simulation control */}
      <div className="buttons-group">
        {/* One button that switches between Start and Stop depending on the current state */}
        {!isRunning ? (
          <button className="btn btn-primary" onClick={onStart}>
            <Play size={16} /> Start
          </button>
        ) : (
          <button className="btn btn-danger" onClick={onStop}>
            <Square size={16} /> Stop
          </button>
        )}
        <button className="btn btn-secondary" onClick={onReset}>
          <RotateCcw size={16} /> Reset
        </button>
      </div>
    </div>
  );
};

export default ControlPanel;
