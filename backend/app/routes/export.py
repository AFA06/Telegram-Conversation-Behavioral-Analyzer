from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.models import ConversationSession, ResponseEvent
from app.services import activity_analyzer, config_service, statistics
from app.services.response_analyzer import response_percentiles, response_stats_by_hour, response_stats_by_weekday
from app.utils.formatting import format_duration

router = APIRouter()


def _bundle(db: Session) -> dict:
    cfg = config_service.get_or_create_config(db)
    overview = statistics.compute_overview(db)
    df = statistics.messages_dataframe(db)
    other_times = [e.response_seconds for e in db.query(ResponseEvent).filter_by(response_role="other").all()]

    return {
        "chat_name": cfg.chat_name,
        "generated_note": "Calculated statistics only. No raw message text is included.",
        "overview": vars(overview),
        "activity": {
            "hourly": activity_analyzer.hourly_activity(df, "both"),
            "weekday": activity_analyzer.weekday_activity(df, "both"),
        },
        "other_response_summary": response_percentiles(other_times),
        "other_response_by_weekday": response_stats_by_weekday(db, "other", cfg.min_sample_size),
        "other_response_by_hour": response_stats_by_hour(db, "other", cfg.min_sample_size),
        "sessions_count": db.query(ConversationSession).count(),
    }


@router.get("/json")
def export_json(db: Session = Depends(get_current_db)) -> dict:
    """Section 31: exports calculated statistics — never raw messages."""
    return _bundle(db)


@router.get("/csv")
def export_csv(
    dataset: str = Query("response_events", pattern="^(response_events|weekday|hourly|sessions)$"),
    db: Session = Depends(get_current_db),
) -> StreamingResponse:
    buf = io.StringIO()

    if dataset == "response_events":
        rows = db.query(ResponseEvent).all()
        writer = csv.writer(buf)
        writer.writerow(["id", "trigger_role", "response_role", "trigger_burst_end", "response_burst_start", "response_seconds", "weekday", "hour"])
        for r in rows:
            writer.writerow([r.id, r.trigger_role, r.response_role, r.trigger_burst_end, r.response_burst_start, r.response_seconds, r.weekday, r.hour])
    elif dataset == "sessions":
        rows = db.query(ConversationSession).all()
        writer = csv.writer(buf)
        writer.writerow(["id", "start_ts", "end_ts", "duration_seconds", "message_count", "me_count", "other_count"])
        for r in rows:
            writer.writerow([r.id, r.start_ts, r.end_ts, r.duration_seconds, r.message_count, r.me_count, r.other_count])
    else:
        df = statistics.messages_dataframe(db)
        data = activity_analyzer.weekday_activity(df, "both") if dataset == "weekday" else activity_analyzer.hourly_activity(df, "both")
        writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()) if data else [])
        writer.writeheader()
        writer.writerows(data)

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={dataset}.csv"},
    )


@router.get("/html", response_class=HTMLResponse)
def export_html(db: Session = Depends(get_current_db)) -> str:
    """Section 31: a simple, self-contained HTML statistics report."""
    b = _bundle(db)
    ov = b["overview"]
    resp = b["other_response_summary"] or {}

    def fmt(seconds_key: str) -> str:
        return format_duration(resp.get(seconds_key))

    rows_weekday = "".join(
        f"<tr><td>{w['name']}</td><td>{w['count']}</td><td>{w['percentage']}%</td></tr>" for w in b["activity"]["weekday"]
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Conversation Report — {b['chat_name'] or ''}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
h1,h2{{border-bottom:1px solid #ddd;padding-bottom:.3rem}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td,th{{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}}
.note{{color:#666;font-size:.9rem}}
</style></head><body>
<h1>Telegram Conversation Report</h1>
<p class="note">{b['generated_note']} This report describes historical communication patterns only — it does not
interpret intent, availability, or feelings.</p>

<h2>Overview</h2>
<table>
<tr><th>Total messages</th><td>{ov['total_messages']}</td></tr>
<tr><th>Me</th><td>{ov['me_messages']} ({ov['me_percentage']}%)</td></tr>
<tr><th>Other person</th><td>{ov['other_messages']} ({ov['other_percentage']}%)</td></tr>
<tr><th>Period</th><td>{ov['first_message_date']} to {ov['last_message_date']}</td></tr>
<tr><th>Active days</th><td>{ov['active_days']}</td></tr>
<tr><th>Conversation sessions</th><td>{b['sessions_count']}</td></tr>
</table>

<h2>Other person's response time</h2>
<table>
<tr><th>Fastest</th><td>{fmt('fastest_seconds')}</td></tr>
<tr><th>Median</th><td>{fmt('median_seconds')}</td></tr>
<tr><th>Average</th><td>{fmt('average_seconds')}</td></tr>
<tr><th>90th percentile</th><td>{fmt('p90_seconds')}</td></tr>
<tr><th>Sample size</th><td>{resp.get('count', 0)}</td></tr>
</table>

<h2>Activity by weekday</h2>
<table><tr><th>Day</th><th>Messages</th><th>%</th></tr>{rows_weekday}</table>

</body></html>"""
