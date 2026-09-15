import { useState } from "react";
import Card from "../components/Card";
import MonthlyTrendChart from "../charts/MonthlyTrendChart";
import { Loading, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";
import { formatDuration } from "../utils/format";

export default function Trends() {
  const monthly = useApi("/trends/monthly");
  const [nMonths, setNMonths] = useState(3);
  const compare = useApi(`/trends/compare?n_months=${nMonths}`);

  const chartData = monthly.data?.map((m) => ({
    month: m.month,
    "Total messages": m.total_messages,
    "Median response (min)": m.median_response_seconds ? Math.round(m.median_response_seconds / 60) : null,
  }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Trends</h1>
          <p>How activity and response times have changed over time. Percentages describe observed patterns only.</p>
        </div>
      </div>

      <Card title="Monthly activity" note="Messages per month across the whole imported history.">
        {monthly.loading ? (
          <Loading />
        ) : chartData?.length ? (
          <MonthlyTrendChart data={chartData} lines={[{ dataKey: "Total messages", name: "Total messages", color: "var(--accent)" }]} />
        ) : (
          <EmptyState>No data yet.</EmptyState>
        )}
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="Median response time by month (minutes)">
        {monthly.loading ? (
          <Loading />
        ) : chartData?.length ? (
          <MonthlyTrendChart data={chartData} lines={[{ dataKey: "Median response (min)", name: "Median response (min)", color: "var(--good)" }]} />
        ) : (
          <EmptyState>No data yet.</EmptyState>
        )}
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="Period comparison" note="First N months vs. last N months. Neutral, factual comparison only.">
        <div className="form-field" style={{ maxWidth: 200 }}>
          <label>Months per period</label>
          <input type="number" min={1} max={24} value={nMonths} onChange={(e) => setNMonths(Number(e.target.value) || 1)} />
        </div>
        {compare.loading ? (
          <Loading />
        ) : compare.data?.note && !compare.data?.first_period ? (
          <EmptyState>{compare.data.note}</EmptyState>
        ) : compare.data ? (
          <table>
            <thead>
              <tr>
                <th></th>
                <th>First {nMonths} months</th>
                <th>Last {nMonths} months</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Total messages</td>
                <td>{compare.data.first_period.total_messages}</td>
                <td>{compare.data.last_period.total_messages}</td>
                <td>{compare.data.message_frequency_change_percent ?? "N/A"}%</td>
              </tr>
              <tr>
                <td>Active days</td>
                <td>{compare.data.first_period.active_days}</td>
                <td>{compare.data.last_period.active_days}</td>
                <td>—</td>
              </tr>
              <tr>
                <td>Median response</td>
                <td>{formatDuration(compare.data.first_period.median_response_seconds)}</td>
                <td>{formatDuration(compare.data.last_period.median_response_seconds)}</td>
                <td>{compare.data.median_response_change_percent ?? "N/A"}%</td>
              </tr>
            </tbody>
          </table>
        ) : null}
      </Card>
    </div>
  );
}
