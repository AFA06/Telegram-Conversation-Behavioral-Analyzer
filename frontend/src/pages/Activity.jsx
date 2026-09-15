import { useState } from "react";
import Card from "../components/Card";
import RoleToggle from "../components/RoleToggle";
import Heatmap from "../charts/Heatmap";
import HourlyBarChart from "../charts/HourlyBarChart";
import WeekdayBarChart from "../charts/WeekdayBarChart";
import { Loading, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";

const WINDOW_SIZES = [
  { label: "30 min", value: 30 },
  { label: "1 hour", value: 60 },
  { label: "2 hours", value: 120 },
  { label: "3 hours", value: 180 },
];

export default function Activity() {
  const [role, setRole] = useState("both");
  const [windowMinutes, setWindowMinutes] = useState(60);

  const hourly = useApi(`/activity/hourly?role=${role}`);
  const weekday = useApi(`/activity/weekday?role=${role}`);
  const heatmap = useApi(`/activity/heatmap?role=${role}`);
  const windows = useApi(`/activity/top-windows?role=${role}&window_minutes=${windowMinutes}&top_n=5`);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Activity</h1>
          <p>When messages historically happen, by hour, weekday, and recurring windows.</p>
        </div>
        <RoleToggle value={role} onChange={setRole} />
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <Card title="Messages by hour of day">{hourly.loading ? <Loading /> : <HourlyBarChart data={hourly.data} />}</Card>
        <Card title="Messages by weekday">{weekday.loading ? <Loading /> : <WeekdayBarChart data={weekday.data} />}</Card>
      </div>

      <Card title="Day × hour heatmap" note="7×24 grid of historical message volume." >
        {heatmap.loading ? <Loading /> : <Heatmap heatmap={heatmap.data} />}
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="Most active recurring windows" note="Ranked by total historical message volume for that recurring weekday/time slot.">
        <div style={{ marginBottom: "0.75rem", display: "flex", gap: "0.4rem" }}>
          {WINDOW_SIZES.map((w) => (
            <button
              key={w.value}
              className={windowMinutes === w.value ? "primary" : "secondary"}
              onClick={() => setWindowMinutes(w.value)}
            >
              {w.label}
            </button>
          ))}
        </div>
        {windows.loading ? (
          <Loading />
        ) : windows.data?.length ? (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Window</th>
                <th>Messages</th>
              </tr>
            </thead>
            <tbody>
              {windows.data.map((w, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td>
                    {w.weekday_name} {w.start_label}-{w.end_label}
                  </td>
                  <td>{w.message_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState>No data yet.</EmptyState>
        )}
      </Card>
    </div>
  );
}
