import { useState } from "react";
import Card from "../components/Card";
import StatTile from "../components/StatTile";
import RoleToggle from "../components/RoleToggle";
import Heatmap from "../charts/Heatmap";
import ConfidenceBadge from "../components/ConfidenceBadge";
import { Loading, ErrorBanner, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";
import { formatDuration } from "../utils/format";

export default function Overview() {
  const { data, error, loading } = useApi("/overview");
  const [heatRole, setHeatRole] = useState("both");
  const heatmapQuery = useApi(`/activity/heatmap?role=${heatRole}`);
  const windowsQuery = useApi("/responses/historically-responsive?top_n=5");

  if (loading) return <Loading />;
  if (error) return <ErrorBanner message={error} />;
  if (!data || data.total_messages === 0) {
    return (
      <EmptyState>
        No conversation imported yet. Head to <b>Settings</b> to import a Telegram export and configure participants.
      </EmptyState>
    );
  }

  const otherName = data.other_display_name || "Other person";

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Overview</h1>
          <p>{data.chat_name || "Imported conversation"} · timezone {data.timezone}</p>
        </div>
      </div>

      <div className="privacy-banner">Your Telegram export stays on this device. Nothing here is sent to any external service.</div>

      <div className="grid grid-cards" style={{ marginBottom: "1.5rem" }}>
        <StatTile label="Total messages" value={data.total_messages.toLocaleString()} />
        <StatTile label={otherName} value={data.other_messages.toLocaleString()} sub={`${data.other_percentage}%`} />
        <StatTile label={data.me_display_name || "Me"} value={data.me_messages.toLocaleString()} sub={`${data.me_percentage}%`} />
        <StatTile label="Active days" value={data.active_days.toLocaleString()} />
        <StatTile label="Conversation sessions" value={data.conversation_sessions.toLocaleString()} />
        <StatTile label={`Median response (${otherName})`} value={formatDuration(data.other_response.median_seconds)} />
        <StatTile label="Fastest response" value={formatDuration(data.other_response.fastest_seconds)} />
        <StatTile label="Longest response" value={formatDuration(data.other_response.slowest_seconds)} />
      </div>

      <div className="grid grid-2">
        <Card
          title="Activity heatmap"
          note="Darker cells = more historical messages in that weekday/hour slot. Not a prediction of future activity."
        >
          <div style={{ marginBottom: "0.75rem" }}>
            <RoleToggle value={heatRole} onChange={setHeatRole} labels={{ me: data.me_display_name, other: otherName, both: "Both" }} />
          </div>
          {heatmapQuery.loading ? <Loading /> : <Heatmap heatmap={heatmapQuery.data} />}
        </Card>

        <Card
          title="Historically responsive windows"
          note={windowsQuery.data?.note || "Based on historical conversations only — not a claim about availability."}
        >
          {windowsQuery.loading ? (
            <Loading />
          ) : windowsQuery.data?.windows?.length ? (
            <table>
              <thead>
                <tr>
                  <th>Window</th>
                  <th>Median response</th>
                  <th>Sample</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {windowsQuery.data.windows.map((w, i) => (
                  <tr key={i}>
                    <td>
                      {w.weekday_name} {w.start_label}-{w.end_label}
                    </td>
                    <td>{formatDuration(w.median_seconds)}</td>
                    <td>{w.sample_size}</td>
                    <td>
                      <ConfidenceBadge level={w.confidence} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState>Not enough response data yet.</EmptyState>
          )}
        </Card>
      </div>
    </div>
  );
}
