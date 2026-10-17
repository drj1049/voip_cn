import React from 'react';

const MetricCard = ({ title, value, subValue, unit = '', color = 'var(--text-primary)', icon: Icon }) => {
  return (
    <div className="card-panel metric-card">
      <div className="card-title">
        <span>{title}</span>
        {Icon && <Icon size={18} color="var(--text-secondary)" />}
      </div>
      <div className="metric-value-box">
        <span className="metric-main-val" style={{ color }}>
          {value !== undefined && value !== null ? value : '--'}
          <span style={{ fontSize: '1rem', marginLeft: '4px', fontWeight: 500, color: 'var(--text-secondary)' }}>
            {unit}
          </span>
        </span>
      </div>
      {subValue && <div className="metric-sub-val">{subValue}</div>}
    </div>
  );
};

export default MetricCard;
