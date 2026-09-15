import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";

export default function MonthlyTrendChart({ data, lines }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="month" stroke="var(--text-faint)" fontSize={11} />
        <YAxis stroke="var(--text-faint)" fontSize={11} allowDecimals={false} />
        <Tooltip contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {lines.map((line) => (
          <Line key={line.dataKey} type="monotone" dataKey={line.dataKey} name={line.name} stroke={line.color} dot={false} strokeWidth={2} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
