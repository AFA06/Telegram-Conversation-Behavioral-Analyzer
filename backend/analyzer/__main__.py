"""Command-line entry point.

Usage (run from the ``backend/`` directory, with the venv active):

    python -m analyzer import path/to/result.json
    python -m analyzer participants   # see the exact sender ids found in the export
    python -m analyzer configure --me-id user111 --me-name Me --other-id user222 --other-name Them
    python -m analyzer analyze
    python -m analyzer stats
    python -m analyzer server

Tip: import first without --me-id/--other-id, run 'participants' to see the
exact id strings Telegram used in your export (they're usually prefixed,
e.g. 'user938613594', not bare '938613594'), then 'configure' with those.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.database import SessionLocal, init_db
from app.services import config_service, statistics
from app.services.importer import import_export_file
from app.services.response_analyzer import response_percentiles, run_full_analysis
from app.utils.formatting import format_duration


def cmd_import(args: argparse.Namespace) -> None:
    init_db()
    db = SessionLocal()
    try:
        if args.me_id and args.other_id:
            config_service.set_participants(
                db,
                me_user_id=args.me_id,
                me_display_name=args.me_name or "Me",
                other_user_id=args.other_id,
                other_display_name=args.other_name or "Other person",
            )
        cfg = config_service.get_or_create_config(db)
        if args.timezone:
            cfg.timezone = args.timezone
            db.commit()

        report = import_export_file(db, args.file, cfg.timezone)
        print(f"Imported: {report.imported_count}")
        print(f"Valid:    {report.valid_count}")
        print(f"Skipped:  {report.skipped_count}")
        if report.skipped_reasons:
            print("Reasons:")
            for reason, count in sorted(report.skipped_reasons.items(), key=lambda kv: -kv[1]):
                print(f"  - {reason}: {count}")

        detected = config_service.detect_participants(db)
        print("\nSenders found in this export (use these exact ids for --me-id/--other-id):")
        for d in detected:
            print(f"  {d['sender_id']:<20} {d['sender_name'] or '(no name)':<20} {d['message_count']} messages")

        if not cfg.me_user_id or not cfg.other_user_id:
            print("\nParticipants are not configured yet. Re-run with --me-id/--other-id using")
            print("one of the ids listed above, or use the Settings page once the dashboard is running.")
        else:
            me_matches = config_service.matched_message_count(db, cfg.me_user_id)
            other_matches = config_service.matched_message_count(db, cfg.other_user_id)
            if me_matches == 0 or other_matches == 0:
                print(
                    f"\nWarning: configured me-id ({cfg.me_user_id}) matched {me_matches} messages, "
                    f"other-id ({cfg.other_user_id}) matched {other_matches} messages. "
                    "Double-check against the senders listed above — Telegram exports usually "
                    "prefix numeric ids, e.g. 'user938613594' rather than bare '938613594'."
                )
    finally:
        db.close()


def cmd_configure(args: argparse.Namespace) -> None:
    init_db()
    db = SessionLocal()
    try:
        cfg = config_service.get_or_create_config(db)
        if args.me_id:
            cfg.me_user_id = args.me_id
        if args.me_name:
            cfg.me_display_name = args.me_name
        if args.other_id:
            cfg.other_user_id = args.other_id
        if args.other_name:
            cfg.other_display_name = args.other_name
        if args.timezone:
            cfg.timezone = args.timezone
        if args.grouping_window is not None:
            cfg.grouping_window_minutes = args.grouping_window
        if args.session_gap is not None:
            cfg.session_gap_hours = args.session_gap
        if args.min_sample is not None:
            cfg.min_sample_size = args.min_sample
        db.commit()
        print("Configuration updated:")
        print(f"  me:     {cfg.me_display_name} ({cfg.me_user_id})")
        print(f"  other:  {cfg.other_display_name} ({cfg.other_user_id})")
        print(f"  tz:     {cfg.timezone}")
        print(f"  grouping window: {cfg.grouping_window_minutes} min")
        print(f"  session gap:     {cfg.session_gap_hours} h")
        print(f"  min sample size: {cfg.min_sample_size}")
    finally:
        db.close()


def cmd_participants(args: argparse.Namespace) -> None:
    init_db()
    db = SessionLocal()
    try:
        detected = config_service.detect_participants(db)
        if not detected:
            print("No messages imported yet.")
            return
        print("Senders found in the imported export (use these exact ids for 'configure'/'import'):")
        for d in detected:
            print(f"  {d['sender_id']:<20} {d['sender_name'] or '(no name)':<20} {d['message_count']} messages")
    finally:
        db.close()


def cmd_analyze(args: argparse.Namespace) -> None:
    init_db()
    db = SessionLocal()
    try:
        result = run_full_analysis(db)
        print(f"Sessions:          {result['sessions']}")
        print(f"Response events:   {result['response_events']}")
        print(f"Unanswered bursts: {result['unanswered_bursts']}")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def cmd_stats(args: argparse.Namespace) -> None:
    init_db()
    db = SessionLocal()
    try:
        cfg = config_service.get_or_create_config(db)
        overview = statistics.compute_overview(db)
        print(f"Chat: {cfg.chat_name or '(unnamed)'}")
        print(f"Total messages: {overview.total_messages}")
        print(f"  {cfg.me_display_name or 'Me'}: {overview.me_messages} ({overview.me_percentage}%)")
        print(f"  {cfg.other_display_name or 'Other'}: {overview.other_messages} ({overview.other_percentage}%)")
        print(f"Period: {overview.first_message_date} -> {overview.last_message_date} ({overview.conversation_span_days} days)")
        print(f"Active days/weeks/months: {overview.active_days} / {overview.active_weeks} / {overview.active_months}")

        from app.models import ResponseEvent

        her_times = [e.response_seconds for e in db.query(ResponseEvent).filter_by(response_role="other").all()]
        if her_times:
            stats = response_percentiles(her_times)
            print(f"\n{cfg.other_display_name or 'Other person'}'s response time (n={stats['count']}):")
            print(f"  Fastest: {format_duration(stats['fastest_seconds'])}")
            print(f"  Median:  {format_duration(stats['median_seconds'])}")
            print(f"  Average: {format_duration(stats['average_seconds'])}")
            print(f"  P90:     {format_duration(stats['p90_seconds'])}")
        else:
            print("\nNo response events yet — run 'python -m analyzer analyze' first.")
    finally:
        db.close()


def cmd_server(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyzer", description="Telegram Conversation Behavioral Analyzer CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Import a Telegram Desktop JSON export")
    p_import.add_argument("file", help="Path to the exported result.json")
    p_import.add_argument("--me-id", help="Telegram user id for 'me'")
    p_import.add_argument("--me-name", help="Display name for 'me'")
    p_import.add_argument("--other-id", help="Telegram user id for the other person")
    p_import.add_argument("--other-name", help="Display name for the other person")
    p_import.add_argument("--timezone", help="IANA timezone, e.g. Asia/Tashkent")
    p_import.set_defaults(func=cmd_import)

    p_cfg = sub.add_parser("configure", help="Update participant identities / analysis settings")
    p_cfg.add_argument("--me-id")
    p_cfg.add_argument("--me-name")
    p_cfg.add_argument("--other-id")
    p_cfg.add_argument("--other-name")
    p_cfg.add_argument("--timezone")
    p_cfg.add_argument("--grouping-window", type=int, help="Message burst grouping window, in minutes")
    p_cfg.add_argument("--session-gap", type=int, help="Inactivity gap that starts a new session, in hours")
    p_cfg.add_argument("--min-sample", type=int, help="Minimum observations required before reporting a window")
    p_cfg.set_defaults(func=cmd_configure)

    p_participants = sub.add_parser("participants", help="List sender ids found in the imported export")
    p_participants.set_defaults(func=cmd_participants)

    p_analyze = sub.add_parser("analyze", help="Compute sessions, response times, and no-response bursts")
    p_analyze.set_defaults(func=cmd_analyze)

    p_stats = sub.add_parser("stats", help="Print a quick summary to the terminal")
    p_stats.set_defaults(func=cmd_stats)

    p_server = sub.add_parser("server", help="Run the FastAPI backend")
    p_server.add_argument("--host", default="127.0.0.1")
    p_server.add_argument("--port", type=int, default=8000)
    p_server.add_argument("--reload", action="store_true")
    p_server.set_defaults(func=cmd_server)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
