import React from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { ShieldAlert } from 'lucide-react';

// Packet loss card: a loss % graph on the left, and the sent / received / lost counts on the right.
const PacketLossCard = ({ data = [], packetsSent = 0, packetsReceived = 0, packetsLost = 0, lossPct = 0 }) => {
  return (
    <div className="card-panel">
      <div className="card-title">
        <span>Packet Loss Timeline & Statistics</span>
        <ShieldAlert size={18} color="var(--accent-red)" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1rem', alignItems: 'center' }}>
        {/* Packet Loss Graph */}
        <div className="chart-container" style={{ height: '180px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tickLine={false} />
              {/* 30 is the highest loss the sliders allow, so the axis is fixed to 0 to 30 */}
              <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 30]} tickLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px', color: '#f8fafc' }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Area
                type="monotone"
                dataKey="packet_loss"
                name="Loss (%)"
                stroke="#ef4444"
                fill="rgba(239, 68, 68, 0.2)"
                strokeWidth={2}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Detailed Packet Breakdown */}
        <div className="pkt-stats-list">
          <div className="pkt-stat-row">
            <span style={{ color: 'var(--text-secondary)' }}>Packets Transmitted</span>
            <strong style={{ fontFamily: 'var(--font-mono)' }}>{packetsSent}</strong>
          </div>
          <div className="pkt-stat-row">
            <span style={{ color: 'var(--text-secondary)' }}>Packets Received</span>
            <strong style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-emerald)' }}>{packetsReceived}</strong>
          </div>
          <div className="pkt-stat-row">
            <span style={{ color: 'var(--text-secondary)' }}>Packets Dropped / Lost</span>
            <strong style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-red)' }}>{packetsLost}</strong>
          </div>
          <div className="pkt-stat-row" style={{ paddingTop: '0.5rem' }}>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Packet Loss Rate</span>
            {/* Goes red above 5% loss, where call quality starts to suffer clearly */}
            <strong style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', color: lossPct > 5 ? 'var(--accent-red)' : 'var(--accent-emerald)' }}>
              {lossPct ? lossPct.toFixed(1) : '0.0'}%
            </strong>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PacketLossCard;
