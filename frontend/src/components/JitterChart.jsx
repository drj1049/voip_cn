import React from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { Waves } from 'lucide-react';

// Line chart of RFC 3550 jitter over time. Same idea as the latency chart.
const JitterChart = ({ data = [] }) => {
  return (
    <div className="card-panel">
      <div className="card-title">
        <span>RFC 3550 Interarrival Jitter (ms)</span>
        <Waves size={18} color="var(--accent-purple)" />
      </div>
      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tickLine={false} />
            <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 'dataMax + 10']} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px', color: '#f8fafc' }}
              labelStyle={{ color: '#94a3b8' }}
            />
            {/* The y-axis top is the biggest value plus 10, so the line never touches the edge */}
            <Line
              type="monotone"
              dataKey="jitter"
              name="Jitter (ms)"
              stroke="#8b5cf6"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default JitterChart;
