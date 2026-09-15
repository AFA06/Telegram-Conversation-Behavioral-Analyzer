import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function HourlyBarChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="hour" tickFormatter={(h) => `${h}`} stroke="var(--text-faint)" fontSize={11} />
        <YAxis stroke="var(--text-faint)" fontSize={11} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", fontSize: 12 }}
          labelFormatter={(h) => `${String(h).padStart(2, "0")}:00`}
        />
        <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
