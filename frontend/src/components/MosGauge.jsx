import React from 'react';
import { Award, Zap } from 'lucide-react';

// The big half-circle gauge showing the MOS score, its rating and the R-factor.
// The defaults are the "perfect line" values, shown until the first live numbers arrive.
const MosGauge = ({ mos = 4.5, quality = 'EXCELLENT', rFactor = 93.2 }) => {
  // Determine color class and hue based on MOS
  const getQualityColor = (rating) => {
    switch (rating) {
      case 'EXCELLENT': return '#10b981';
      case 'GOOD': return '#06b6d4';
      case 'FAIR': return '#f59e0b';
      case 'POOR': return '#f97316';
      case 'BAD': return '#ef4444';
      default: return '#3b82f6';
    }
  };

  const currentColor = getQualityColor(quality);
  // Turn the MOS into how full the arc should be: 1.0 = empty, 4.5 = full (that is the 3.5 range).
  // Math.min/max keep it between 0 and 100 even if a strange value arrives.
  // Calculate percentage fill for gauge (MOS ranges 1.0 to 4.5/5.0)
  const percent = Math.min(100, Math.max(0, ((mos - 1.0) / 3.5) * 100));

  return (
    <div className="card-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <div className="card-title">
        <span>VoIP MOS & Quality Status</span>
        <Award size={20} color={currentColor} />
      </div>

      <div className="mos-gauge-wrapper">
        {/* SVG Arc Meter */}
        <div style={{ position: 'relative', width: '180px', height: '100px', margin: '0 auto 0.5rem auto' }}>
          <svg viewBox="0 0 100 50" style={{ width: '100%', height: '100%' }}>
            {/* Background Track */}
            <path
              d="M 10 50 A 40 40 0 0 1 90 50"
              fill="none"
              stroke="#334155"
              strokeWidth="8"
              strokeLinecap="round"
            />
            {/* Active Arc Progress.
                125.6 is the length of this half-circle (pi x radius 40). strokeDashoffset hides
                the part of the line that should be empty, so a smaller offset = a fuller arc. */}
            <path
              d="M 10 50 A 40 40 0 0 1 90 50"
              fill="none"
              stroke={currentColor}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray="125.6"
              strokeDashoffset={125.6 - (125.6 * percent) / 100}
              style={{ transition: 'stroke-dashoffset 0.3s ease, stroke 0.3s ease' }}
            />
          </svg>
        </div>

        <div className="mos-score-large" style={{ color: currentColor }}>
          {/* toFixed(2) = always show two decimals, like 3.91 */}
          {mos ? mos.toFixed(2) : '1.00'}
        </div>

        <div className={`quality-badge-lg quality-${quality}`}>
          {quality} QUALITY
        </div>

        <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'center' }}>
          <Zap size={14} color="var(--accent-amber)" />
          <span>ITU-T G.107 R-Factor: <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{rFactor ? rFactor.toFixed(1) : '0.0'}</strong> / 100</span>
        </div>
      </div>
    </div>
  );
};

export default MosGauge;
