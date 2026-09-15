export default function Heatmap({ heatmap }) {
  if (!heatmap || !heatmap.grid) return null;
  const { weekdays, hours, grid, max_count: max } = heatmap;

  const colorFor = (value) => {
    if (!max || value === 0) return "var(--bg-elevated)";
    const intensity = Math.sqrt(value / max); // sqrt scale: keeps low-activity cells visible
    const alpha = 0.12 + intensity * 0.78;
    return `rgba(91, 140, 255, ${alpha.toFixed(2)})`;
  };

  return (
    <div>
      <div className="heatmap" style={{ marginBottom: 2 }}>
        <div />
        {hours.map((h) => (
          <div key={h} className="hour-label">
            {h % 3 === 0 ? h : ""}
          </div>
        ))}
      </div>
      {weekdays.map((day, rowIdx) => (
        <div className="heatmap" key={day}>
          <div className="hlabel">{day.slice(0, 3)}</div>
          {hours.map((h) => {
            const value = grid[rowIdx][h];
            return (
              <div
                key={h}
                className="hcell"
                title={`${day} ${String(h).padStart(2, "0")}:00 — ${value} messages`}
                style={{ background: colorFor(value) }}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}
