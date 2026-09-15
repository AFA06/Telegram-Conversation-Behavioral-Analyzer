import { useState } from "react";
import Card from "../components/Card";
import StatTile from "../components/StatTile";
import { Loading, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";
import { formatDuration } from "../utils/format";

export default function Conversations() {
  const [sortBy, setSortBy] = useState("duration");
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const summary = useApi("/sessions/summary");
  const longest = useApi(`/sessions/longest?by=${sortBy}&limit=10`);
  const list = useApi(`/sessions?limit=${pageSize}&offset=${page * pageSize}`);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Conversations</h1>
          <p>A new session starts after a period of inactivity (configurable in Settings).</p>
        </div>
      </div>

      {summary.loading ? (
        <Loading />
      ) : summary.data?.count ? (
        <div className="grid grid-cards" style={{ marginBottom: "1rem" }}>
          <StatTile label="Sessions" value={summary.data.count} />
          <StatTile label="Average duration" value={formatDuration(summary.data.average_duration_seconds)} />
          <StatTile label="Median duration" value={formatDuration(summary.data.median_duration_seconds)} />
          <StatTile label="Longest session" value={formatDuration(summary.data.longest_duration_seconds)} />
          <StatTile label="Avg. messages / session" value={summary.data.average_messages_per_session} />
        </div>
      ) : (
        <EmptyState>No sessions yet.</EmptyState>
      )}

      <Card title="Longest conversations">
        <div style={{ marginBottom: "0.75rem", display: "flex", gap: "0.4rem" }}>
          <button className={sortBy === "duration" ? "primary" : "secondary"} onClick={() => setSortBy("duration")}>
            By duration
          </button>
          <button className={sortBy === "messages" ? "primary" : "secondary"} onClick={() => setSortBy("messages")}>
            By message count
          </button>
        </div>
        {longest.loading ? (
          <Loading />
        ) : longest.data?.length ? (
          <table>
            <thead>
              <tr>
                <th>Start</th>
                <th>End</th>
                <th>Duration</th>
                <th>Messages</th>
              </tr>
            </thead>
            <tbody>
              {longest.data.map((s) => (
                <tr key={s.id}>
                  <td>{new Date(s.start_ts).toLocaleString()}</td>
                  <td>{new Date(s.end_ts).toLocaleString()}</td>
                  <td>{s.duration_formatted}</td>
                  <td>
                    {s.message_count} ({s.me_count} / {s.other_count})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState>No sessions yet.</EmptyState>
        )}
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="All sessions" note={list.data ? `${list.data.total} total` : undefined}>
        {list.loading ? (
          <Loading />
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>Start</th>
                  <th>Duration</th>
                  <th>Messages</th>
                </tr>
              </thead>
              <tbody>
                {list.data?.items.map((s) => (
                  <tr key={s.id}>
                    <td>{new Date(s.start_ts).toLocaleString()}</td>
                    <td>{s.duration_formatted}</td>
                    <td>
                      {s.message_count} ({s.me_count} / {s.other_count})
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
              <button className="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <button
                className="secondary"
                disabled={!list.data || (page + 1) * pageSize >= list.data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
