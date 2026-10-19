import React from 'react';

// One of the four small cards under the gauge (Latency, Jitter, Packet loss, MOS).
// title: heading, value + unit: the big number, subValue: the small grey line under it,
// color: colour of the big number, icon: a lucide icon component for the corner.
const MetricCard = ({ title, value, subValue, unit = '', color = 'var(--text-primary)', icon: Icon }) => {
  return (
    <div className="card-panel metric-card">
      <div className="card-title">
        <span>{title}</span>
        {Icon && <Icon size={18} color="var(--text-secondary)" />}
      </div>
      <div className="metric-value-box">
        <span className="metric-main-val" style={{ color }}>
          {/* Show -- if the number is not available yet, instead of "undefined" */}
          {value !== undefined && value !== null ? value : '--'}
          <span style={{ fontSize: '1rem', marginLeft: '4px', fontWeight: 500, color: 'var(--text-secondary)' }}>
            {unit}
          </span>
        </span>
      </div>
      {/* The small line is optional, so only draw it when there is something to say */}
      {subValue && <div className="metric-sub-val">{subValue}</div>}
    </div>
  );
};

export default MetricCard;
