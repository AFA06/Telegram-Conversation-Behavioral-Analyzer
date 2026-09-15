import { useState } from "react";
import Card from "../components/Card";
import StatTile from "../components/StatTile";
import RoleToggle from "../components/RoleToggle";
import ConfidenceBadge from "../components/ConfidenceBadge";
import ResponseDistributionChart from "../charts/ResponseDistributionChart";
import { Loading, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";
import { formatDuration, WEEKDAY_NAMES } from "../utils/format";

export default function ResponseTimes() {
  const [role, setRole] = useState("other");

  const summary = useApi(`/responses/summary?role=${role}`);
  const fastest = useApi(`/responses/fastest?role=${role}&limit=10`);
  const longest = useApi(`/responses/longest?role=${role}&limit=20`);
  const byWeekday = useApi(`/responses/by-weekday?role=${role}`);
  const byHour = useApi(`/responses/by-hour?role=${role}`);
  const unanswered = useApi(`/responses/unanswered?role=${role === "other" ? "me" : "other"}`);

  const stats = summary.data?.stats;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Response Times</h1>
          <p>How quickly each person has historically replied. Delays describe timing only — never intent.</p>
        </div>
        <RoleToggle value={role} onChange={setRole} options={["me", "other"]} labels={{ me: "My replies", other: "Their replies" }} />
      </div>

      {summary.loading ? (
        <Loading />
      ) : stats && stats.count ? (
        <div className="grid grid-cards" style={{ marginBottom: "1rem" }}>
          <StatTile label="Fastest" value={formatDuration(stats.fastest_seconds)} />
          <StatTile label="Median" value={formatDuration(stats.median_seconds)} />
          <StatTile label="Average" value={formatDuration(stats.average_seconds)} />
          <StatTile label="25th pct" value={formatDuration(stats.p25_seconds)} />
          <StatTile label="75th pct" value={formatDuration(stats.p75_seconds)} />
          <StatTile label="90th pct" value={formatDuration(stats.p90_seconds)} />
          <StatTile label="Longest" value={formatDuration(stats.slowest_seconds)} />
          <StatTile label="Sample size" value={stats.count} />
        </div>
      ) : (
        <EmptyState>No response events yet — import a conversation and configure participants in Settings.</EmptyState>
      )}

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <Card title="Response time distribution" note="Median is a better summary than average, since response times are usually skewed.">
          {summary.loading ? <Loading /> : <ResponseDistributionChart data={summary.data?.distribution || []} />}
        </Card>

        <Card title="By weekday" note="Buckets below the minimum sample size are marked insufficient rather than guessed.">
          {byWeekday.loading ? (
            <Loading />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Median</th>
                  <th>n</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {byWeekday.data?.map((r) => (
                  <tr key={r.weekday}>
                    <td>{r.name}</td>
                    <td>{r.sufficient_data ? formatDuration(r.median_seconds) : "Insufficient data"}</td>
                    <td>{r.sample_size}</td>
                    <td>{r.sufficient_data && <ConfidenceBadge level={r.confidence} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card title="By hour of day" note="Hour of the trigger message, in the configured local timezone.">
        {byHour.loading ? (
          <Loading />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Hour</th>
                <th>Median</th>
                <th>n</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {byHour.data
                ?.filter((r) => r.sample_size > 0)
                .map((r) => (
                  <tr key={r.hour}>
                    <td>{String(r.hour).padStart(2, "0")}:00</td>
                    <td>{r.sufficient_data ? formatDuration(r.median_seconds) : "Insufficient data"}</td>
                    <td>{r.sample_size}</td>
                    <td>{r.sufficient_data && <ConfidenceBadge level={r.confidence} />}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </Card>

      <div style={{ height: "1rem" }} />

      <div className="grid grid-2">
        <Card title="Fastest responses">
          {fastest.loading ? (
            <Loading />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>When</th>
                  <th>Delay</th>
                </tr>
              </thead>
              <tbody>
                {fastest.data?.map((e, i) => (
                  <tr key={e.id}>
                    <td>{i + 1}</td>
                    <td>{WEEKDAY_NAMES[e.weekday]} {new Date(e.trigger_burst_end).toLocaleString()}</td>
                    <td>{e.response_formatted}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Longest observed response delays" note="Describes observed timing only — the data cannot prove intentional delay.">
          {longest.loading ? (
            <Loading />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>When</th>
                  <th>Delay</th>
                </tr>
              </thead>
              <tbody>
                {longest.data?.map((e, i) => (
                  <tr key={e.id}>
                    <td>{i + 1}</td>
                    <td>{WEEKDAY_NAMES[e.weekday]} {new Date(e.trigger_burst_end).toLocaleString()}</td>
                    <td>{e.response_formatted}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div style={{ height: "1rem" }} />

      <Card
        title="Messages without a subsequent response"
        note={unanswered.data?.explanation}
      >
        {unanswered.loading ? (
          <Loading />
        ) : (
          <>
            <div className="grid grid-cards" style={{ marginBottom: "0.75rem" }}>
              {Object.entries(unanswered.data?.by_classification || {}).map(([k, v]) => (
                <StatTile key={k} label={k.replaceAll("_", " ")} value={v} />
              ))}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
