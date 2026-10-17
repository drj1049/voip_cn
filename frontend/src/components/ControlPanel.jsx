import React from 'react';
import { Play, Square, RotateCcw, Sliders, Sparkles } from 'lucide-react';

const SCENARIOS = [
  { name: 'Good network', delay: 20, jitter: 2, loss: 0 },
  { name: 'High latency', delay: 200, jitter: 5, loss: 0 },
  { name: 'High jitter', delay: 50, jitter: 60, loss: 0 },
  { name: 'Packet loss', delay: 50, jitter: 10, loss: 10 },
  { name: 'Poor network', delay: 250, jitter: 80, loss: 15 }
];

const ControlPanel = ({
  config,
  onConfigChange,
  isRunning,
  onStart,
  onStop,
  onReset
}) => {
  const setField = (field, value) => {
    onConfigChange({ ...config, [field]: value });
  };

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

  const isActive = (s) =>
    config.delay_ms === s.delay &&
    config.jitter_ms === s.jitter &&
    config.packet_loss_pct === s.loss;

  const lossMode = config.loss_mode === 'burst' ? 'burst' : 'random';
  const bufferMode = config.buffer_mode || 'off';

  const advancedSummary = [
    lossMode === 'burst' ? `Bursty loss (${config.burst_length} packets)` : 'Random loss',
    bufferMode === 'fixed'
      ? `Fixed buffer ${config.buffer_ms} ms`
      : bufferMode === 'adaptive'
      ? 'Adaptive buffer'
      : 'No buffer'
  ].join(' · ');

  // Helpers that return markup (not components), so sliders keep focus while dragging
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

      {/* Advanced settings, collapsed by default */}
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

          {bufferMode === 'fixed' &&
            renderSlider('Buffer depth', 'buffer_ms', ' ms', 0, 200, 5)}
        </div>
      </details>

      {/* Simulation control */}
      <div className="buttons-group">
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
