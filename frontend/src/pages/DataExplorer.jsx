import { useState } from "react";
import Card from "../components/Card";
import { Loading, EmptyState } from "../components/Status";
import useApi from "../hooks/useApi";

const MESSAGE_TYPES = ["text", "photo", "video", "voice_message", "video_message", "sticker", "animation", "audio", "file", "empty"];

export default function DataExplorer() {
  const [filters, setFilters] = useState({ sender: "", weekday: "", hour: "", message_type: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => v !== "" && params.set(k, v));
  params.set("limit", pageSize);
  params.set("offset", page * pageSize);

  const messages = useApi(`/messages?${params.toString()}`);

  const update = (key, value) => {
    setPage(0);
    setFilters((f) => ({ ...f, [key]: value }));
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Data Explorer</h1>
          <p>Browse the imported messages directly, with filters.</p>
        </div>
      </div>

      <Card title="Filters">
        <div className="grid grid-cards">
          <div className="form-field">
            <label>Sender</label>
            <select value={filters.sender} onChange={(e) => update("sender", e.target.value)}>
              <option value="">Both</option>
              <option value="me">Me</option>
              <option value="other">Other person</option>
            </select>
          </div>
          <div className="form-field">
            <label>Weekday</label>
            <select value={filters.weekday} onChange={(e) => update("weekday", e.target.value)}>
              <option value="">Any</option>
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => (
                <option key={i} value={i}>
                  {d}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label>Hour</label>
            <select value={filters.hour} onChange={(e) => update("hour", e.target.value)}>
              <option value="">Any</option>
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label>Message type</label>
            <select value={filters.message_type} onChange={(e) => update("message_type", e.target.value)}>
              <option value="">Any</option>
              {MESSAGE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label>From date</label>
            <input type="date" value={filters.date_from} onChange={(e) => update("date_from", e.target.value)} />
          </div>
          <div className="form-field">
            <label>To date</label>
            <input type="date" value={filters.date_to} onChange={(e) => update("date_to", e.target.value)} />
          </div>
        </div>
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="Messages" note={messages.data ? `${messages.data.total} matching messages` : undefined}>
        {messages.loading ? (
          <Loading />
        ) : messages.data?.items.length ? (
          <>
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Sender</th>
                  <th>Type</th>
                  <th>Text</th>
                </tr>
              </thead>
              <tbody>
                {messages.data.items.map((m) => (
                  <tr key={m.id}>
                    <td>{new Date(m.timestamp_local).toLocaleString()}</td>
                    <td>{m.sender_role === "me" ? "Me" : "Other"}</td>
                    <td>{m.message_type}</td>
                    <td style={{ maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.text}</td>
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
                disabled={(page + 1) * pageSize >= messages.data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </>
        ) : (
          <EmptyState>No messages match these filters.</EmptyState>
        )}
      </Card>
    </div>
  );
}
