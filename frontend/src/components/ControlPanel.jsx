import React from 'react';
import { Play, Square, RotateCcw, Sliders, Sparkles } from 'lucide-react';

const ControlPanel = ({
  config,
  onConfigChange,
  isRunning,
  onStart,
  onStop,
  onReset
}) => {
  const handleSliderChange = (field, value) => {
    onConfigChange({
      ...config,
      [field]: parseFloat(value)
    });
  };

  const setField = (field, value) => {
    onConfigChange({ ...config, [field]: value });
  };

  const toggleStyle = (active) =>
    active
      ? { borderColor: 'var(--accent-blue)', color: 'var(--accent-blue)' }
      : {};

  // Presets only change delay, jitter and loss; the loss pattern and
  // jitter buffer settings stay as the user left them.
  const applyPreset = (delay, jitter, loss) => {
    onConfigChange({
      ...config,
      delay_ms: delay,
      jitter_ms: jitter,
      packet_loss_pct: loss
    });
  };

  return (
    <div className="card-panel">
      <div className="card-title">
        <span>Network Impairment Control Panel</span>
        <Sliders size={18} color="var(--accent-blue)" />
      </div>

      {/* Sliders Group */}
      <div className="sliders-group">
        <div className="slider-item">
          <label>
            <span>Delay (Latency)</span>
            <span className="val">{config.delay_ms} ms</span>
          </label>
          <input
            type="range"
            min="0"
            max="500"
            step="5"
            value={config.delay_ms}
            onChange={(e) => handleSliderChange('delay_ms', e.target.value)}
            className="custom-slider"
          />
        </div>

        <div className="slider-item">
          <label>
            <span>Jitter (Delay Variation)</span>
            <span className="val">{config.jitter_ms} ms</span>
          </label>
          <input
            type="range"
            min="0"
            max="100"
            step="1"
            value={config.jitter_ms}
            onChange={(e) => handleSliderChange('jitter_ms', e.target.value)}
            className="custom-slider"
          />
        </div>

        <div className="slider-item">
          <label>
            <span>Packet Loss</span>
            <span className="val">{config.packet_loss_pct}%</span>
          </label>
          <input
            type="range"
            min="0"
            max="30"
            step="0.5"
            value={config.packet_loss_pct}
            onChange={(e) => handleSliderChange('packet_loss_pct', e.target.value)}
            className="custom-slider"
          />
        </div>

        {/* Loss pattern: random or bursty */}
        <div className="slider-item">
          <label>
            <span>Loss Pattern</span>
            <span className="val">{config.loss_mode === 'burst' ? 'Bursty' : 'Random'}</span>
          </label>
          <div className="preset-buttons-grid">
            <button
              className="preset-btn"
              style={toggleStyle(config.loss_mode !== 'burst')}
              onClick={() => setField('loss_mode', 'random')}
            >
              Random drops
            </button>
            <button
              className="preset-btn"
              style={toggleStyle(config.loss_mode === 'burst')}
              onClick={() => setField('loss_mode', 'burst')}
            >
              Bursty drops
            </button>
          </div>
        </div>

        {config.loss_mode === 'burst' && (
          <div className="slider-item">
            <label>
              <span>Average Burst Length</span>
              <span className="val">{config.burst_length} packets</span>
            </label>
            <input
              type="range"
              min="1"
              max="20"
              step="1"
              value={config.burst_length}
              onChange={(e) => handleSliderChange('burst_length', e.target.value)}
              className="custom-slider"
            />
          </div>
        )}

        {/* Receiver jitter buffer */}
        <div className="slider-item">
          <label>
            <span>Jitter Buffer</span>
            <span className="val">
              {config.buffer_mode === 'fixed'
                ? `Fixed ${config.buffer_ms} ms`
                : config.buffer_mode === 'adaptive'
                ? 'Adaptive'
                : 'Off'}
            </span>
          </label>
          <div className="preset-buttons-grid">
            <button
              className="preset-btn"
              style={toggleStyle(config.buffer_mode === 'off' || !config.buffer_mode)}
              onClick={() => setField('buffer_mode', 'off')}
            >
              Off
            </button>
            <button
              className="preset-btn"
              style={toggleStyle(config.buffer_mode === 'fixed')}
              onClick={() => setField('buffer_mode', 'fixed')}
            >
              Fixed
            </button>
            <button
              className="preset-btn"
              style={toggleStyle(config.buffer_mode === 'adaptive')}
              onClick={() => setField('buffer_mode', 'adaptive')}
            >
              Adaptive
            </button>
          </div>
        </div>

        {config.buffer_mode === 'fixed' && (
          <div className="slider-item">
            <label>
              <span>Buffer Depth</span>
              <span className="val">{config.buffer_ms} ms</span>
            </label>
            <input
              type="range"
              min="0"
              max="200"
              step="5"
              value={config.buffer_ms}
              onChange={(e) => handleSliderChange('buffer_ms', e.target.value)}
              className="custom-slider"
            />
          </div>
        )}
      </div>

      {/* Simulation Control Buttons */}
      <div className="buttons-group">
        {!isRunning ? (
          <button className="btn btn-primary" onClick={onStart}>
            <Play size={16} /> START SIMULATION
          </button>
        ) : (
          <button className="btn btn-danger" onClick={onStop}>
            <Square size={16} /> STOP SIMULATION
          </button>
        )}
        <button className="btn btn-secondary" onClick={onReset}>
          <RotateCcw size={16} /> RESET
        </button>
      </div>

      {/* Quick scenarios */}
      <div className="presets-container">
        <div className="presets-title" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <Sparkles size={13} color="var(--accent-amber)" />
          <span>Quick Scenarios</span>
        </div>
        <div className="preset-buttons-grid">
          <button className="preset-btn" onClick={() => applyPreset(20, 2, 0)}>
            Good network (20 ms, 2 ms, 0%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(200, 5, 0)}>
            High latency (200 ms, 5 ms, 0%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(50, 60, 0)}>
            High jitter (50 ms, 60 ms, 0%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(50, 10, 10)}>
            Packet loss (50 ms, 10 ms, 10%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(250, 80, 15)}>
            Poor network (250 ms, 80 ms, 15%)
          </button>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
