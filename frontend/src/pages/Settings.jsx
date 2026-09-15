import { useEffect, useState } from "react";
import Card from "../components/Card";
import useApi from "../hooks/useApi";
import api from "../api/client";

const TIMEZONES = [
  "Asia/Tashkent",
  "Asia/Almaty",
  "Asia/Bishkek",
  "Asia/Dushanbe",
  "Europe/Moscow",
  "Europe/London",
  "Europe/Istanbul",
  "Asia/Dubai",
  "UTC",
];

export default function Settings() {
  const configQuery = useApi("/config");
  const participantsQuery = useApi("/import/participants");
  const [form, setForm] = useState(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (configQuery.data) setForm(configQuery.data);
  }, [configQuery.data]);

  if (!form) return null;

  const pickAs = (role, sender) => {
    if (role === "me") {
      setForm((f) => ({ ...f, me_user_id: sender.sender_id, me_display_name: sender.sender_name || f.me_display_name }));
    } else {
      setForm((f) => ({ ...f, other_user_id: sender.sender_id, other_display_name: sender.sender_name || f.other_display_name }));
    }
  };

  const update = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const saveParticipants = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await api.put("/config/participants", {
        me_user_id: form.me_user_id,
        me_display_name: form.me_display_name,
        other_user_id: form.other_user_id,
        other_display_name: form.other_display_name,
      });
      setMessage({ type: "ok", text: "Participants saved." });
    } catch (e) {
      setMessage({ type: "err", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await api.put("/config/settings", {
        timezone: form.timezone,
        grouping_window_minutes: Number(form.grouping_window_minutes),
        session_gap_hours: Number(form.session_gap_hours),
        min_sample_size: Number(form.min_sample_size),
      });
      setMessage({ type: "ok", text: "Settings saved. Re-run analysis to apply to response times / sessions." });
    } catch (e) {
      setMessage({ type: "err", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const doImport = async () => {
    if (!file) return;
    setBusy(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const result = await api.post("/import", fd);
      participantsQuery.reload();
      let text = `Imported ${result.valid_count} of ${result.imported_count} messages (${result.skipped_count} skipped). `;
      if (result.analysis) {
        text += `Analysis complete: ${result.analysis.sessions} sessions, ${result.analysis.response_events} response events.`;
      } else if (result.analysis_error) {
        text += `Analysis could not run: ${result.analysis_error}`;
      } else {
        text += "Pick 'Me' and 'Other person' below from the detected senders, then save and re-analyze.";
      }
      setMessage({ type: result.analysis_error ? "err" : "ok", text });
    } catch (e) {
      setMessage({ type: "err", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const reanalyze = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.post("/import/analyze", {});
      setMessage({ type: "ok", text: `Re-analyzed: ${result.sessions} sessions, ${result.response_events} response events, ${result.unanswered_bursts} unanswered bursts.` });
    } catch (e) {
      setMessage({ type: "err", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Import your export, choose the two participants, and tune how conversations are analyzed.</p>
        </div>
      </div>

      <div className="privacy-banner">
        Your Telegram export stays on this device. No message content is sent to any external service, ever, by default.
      </div>

      {message && <div className={message.type === "err" ? "error-banner" : "privacy-banner"}>{message.text}</div>}

      <Card title="1. Import a Telegram export">
        <div className="form-field">
          <label>Telegram Desktop JSON export (result.json)</label>
          <input type="file" accept="application/json" onChange={(e) => setFile(e.target.files[0])} />
        </div>
        <button className="primary" disabled={!file || busy} onClick={doImport}>
          Import
        </button>
      </Card>

      <div style={{ height: "1rem" }} />

      <Card
        title="2. Who is who"
        note="Identities are never guessed — pick from the senders actually found in your export (Telegram ids are usually prefixed, e.g. 'user938613594', not bare '938613594')."
      >
        {participantsQuery.data?.length > 0 && (
          <div style={{ marginBottom: "1rem" }}>
            <table>
              <thead>
                <tr>
                  <th>Sender id</th>
                  <th>Name in export</th>
                  <th>Messages</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {participantsQuery.data.map((s) => (
                  <tr key={s.sender_id}>
                    <td>{s.sender_id}</td>
                    <td>{s.sender_name || "(no name)"}</td>
                    <td>{s.message_count}</td>
                    <td style={{ display: "flex", gap: "0.4rem" }}>
                      <button className="secondary" onClick={() => pickAs("me", s)}>
                        Use as Me
                      </button>
                      <button className="secondary" onClick={() => pickAs("other", s)}>
                        Use as Other
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="grid grid-2">
          <div>
            <div className="form-field">
              <label>My user id</label>
              <input value={form.me_user_id || ""} onChange={(e) => update("me_user_id", e.target.value)} placeholder="e.g. 938613594" />
            </div>
            <div className="form-field">
              <label>My display name</label>
              <input value={form.me_display_name || ""} onChange={(e) => update("me_display_name", e.target.value)} placeholder="Me" />
            </div>
          </div>
          <div>
            <div className="form-field">
              <label>Other person's user id</label>
              <input value={form.other_user_id || ""} onChange={(e) => update("other_user_id", e.target.value)} placeholder="e.g. 6424173522" />
            </div>
            <div className="form-field">
              <label>Other person's display name</label>
              <input value={form.other_display_name || ""} onChange={(e) => update("other_display_name", e.target.value)} placeholder="Other person" />
            </div>
          </div>
        </div>
        <button className="primary" disabled={busy || !form.me_user_id || !form.other_user_id} onClick={saveParticipants}>
          Save participants
        </button>
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="3. Analysis settings">
        <div className="grid grid-2">
          <div className="form-field">
            <label>Timezone</label>
            <select value={form.timezone} onChange={(e) => update("timezone", e.target.value)}>
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label>Message burst grouping window (minutes)</label>
            <input type="number" min={1} max={120} value={form.grouping_window_minutes} onChange={(e) => update("grouping_window_minutes", e.target.value)} />
          </div>
          <div className="form-field">
            <label>New session after inactivity (hours)</label>
            <input type="number" min={1} max={72} value={form.session_gap_hours} onChange={(e) => update("session_gap_hours", e.target.value)} />
          </div>
          <div className="form-field">
            <label>Minimum sample size for windows</label>
            <input type="number" min={1} max={1000} value={form.min_sample_size} onChange={(e) => update("min_sample_size", e.target.value)} />
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.6rem" }}>
          <button className="primary" disabled={busy} onClick={saveSettings}>
            Save settings
          </button>
          <button className="secondary" disabled={busy} onClick={reanalyze}>
            Re-run analysis
          </button>
        </div>
      </Card>

      <div style={{ height: "1rem" }} />

      <Card title="Export" note="Exports calculated statistics only — never raw message text, unless you open Data Explorer yourself.">
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
          <a className="secondary" style={{ textDecoration: "none", padding: "0.55rem 1rem", borderRadius: 8, border: "1px solid var(--border)" }} href="/api/export/json" target="_blank" rel="noreferrer">
            Download JSON
          </a>
          <a className="secondary" style={{ textDecoration: "none", padding: "0.55rem 1rem", borderRadius: 8, border: "1px solid var(--border)" }} href="/api/export/csv?dataset=response_events" target="_blank" rel="noreferrer">
            Download response events CSV
          </a>
          <a className="secondary" style={{ textDecoration: "none", padding: "0.55rem 1rem", borderRadius: 8, border: "1px solid var(--border)" }} href="/api/export/html" target="_blank" rel="noreferrer">
            Open HTML report
          </a>
        </div>
      </Card>
    </div>
  );
}
