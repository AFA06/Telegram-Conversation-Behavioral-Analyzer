import { useEffect, useState } from "react";
import Card from "../components/Card";
import { Loading, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";

export default function Calendar() {
  const months = useApi("/activity/available-months");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (months.data?.length && !selected) {
      const last = months.data[months.data.length - 1];
      setSelected(`${last.year}-${last.month}`);
    }
  }, [months.data, selected]);

  const [year, month] = selected ? selected.split("-").map(Number) : [null, null];
  const daily = useApi(year ? `/activity/daily?year=${year}&month=${month}` : null, { skip: !year });

  const maxTotal = daily.data ? Math.max(1, ...daily.data.map((d) => d.total)) : 1;
  const monthLabel = year ? new Date(year, month - 1, 1).toLocaleString(undefined, { month: "long", year: "numeric" }) : "";

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Calendar</h1>
          <p>Daily message volume for a selected month.</p>
        </div>
        {months.data?.length > 0 && (
          <select value={selected || ""} onChange={(e) => setSelected(e.target.value)}>
            {months.data.map((m) => (
              <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>
                {new Date(m.year, m.month - 1, 1).toLocaleString(undefined, { month: "long", year: "numeric" })}
              </option>
            ))}
          </select>
        )}
      </div>

      <Card title={monthLabel || "No data"}>
        {!months.data?.length ? (
          <EmptyState>No conversation imported yet.</EmptyState>
        ) : daily.loading ? (
          <Loading />
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(34px, 1fr))",
              gap: 4,
            }}
          >
            {daily.data?.map((d) => (
              <div
                key={d.day}
                title={`Day ${d.day}: ${d.total} messages (${d.me_count} me / ${d.other_count} them)`}
                style={{
                  aspectRatio: 1,
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  color: "var(--text-muted)",
                  background: d.total === 0 ? "var(--bg-elevated)" : `rgba(91, 140, 255, ${0.15 + 0.75 * (d.total / maxTotal)})`,
                }}
              >
                {d.day}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
