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

  const applyPreset = (delay, jitter, loss) => {
    onConfigChange({
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

      {/* Predefined Review 2 Demo Scenarios */}
      <div className="presets-container">
        <div className="presets-title" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <Sparkles size={13} color="var(--accent-amber)" />
          <span>Review 2 Demo Scenarios</span>
        </div>
        <div className="preset-buttons-grid">
          <button className="preset-btn" onClick={() => applyPreset(20, 2, 0)}>
            1. Good Network (20ms/2ms/0%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(200, 5, 0)}>
            2. High Latency (200ms/5ms/0%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(50, 60, 0)}>
            3. High Jitter (50ms/60ms/0%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(50, 10, 10)}>
            4. Packet Loss (50ms/10ms/10%)
          </button>
          <button className="preset-btn" onClick={() => applyPreset(250, 80, 15)}>
            5. Poor Network (250ms/80ms/15%)
          </button>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
