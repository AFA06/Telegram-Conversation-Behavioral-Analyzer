import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function ResponseDistributionChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 30 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="bucket" angle={-35} textAnchor="end" interval={0} stroke="var(--text-faint)" fontSize={10} height={55} />
        <YAxis stroke="var(--text-faint)" fontSize={11} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", fontSize: 12 }}
          formatter={(value, name, props) => [`${value} (${props.payload.percentage}%)`, "count"]}
        />
        <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
