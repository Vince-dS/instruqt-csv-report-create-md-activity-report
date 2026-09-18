#!/usr/bin/env python3
from __future__ import annotations
"""
extract_activity.py — Generate a Markdown activity report from an Instruqt participant CSV export.

Each row in the CSV represents one track attempt per user. The same user can appear
multiple times for the same track (retries). A track is "completed" when
track_completed_at is non-empty. All timestamps in the source CSV are UTC and are
converted to the local machine timezone in the report.

Output is a Markdown report with two parts:
  Part 1 — Summary (always included):
    - Tracks — Indicators of Progression section  (opt-in:  --progress-indicator)
    - Track Summary table                          (opt-out: --no-tracks-summary)
    - Per-user Summary table                       (always shown)
  Part 2 — Per-user track detail                  (opt-out: --summary-only)

Options:
  input                      Input CSV file (Instruqt participant export)
  -o, --output FILE          Write report to FILE instead of stdout
  -d, --date YYYY-MM-DD      Filter rows to a specific date (based on last_activity_at)
  --summary-only             Output Part 1 only (skip per-user track detail)
  --no-email                 Omit the Email column from all tables
  --inactive                 Add an 'Inactive For' column showing the time elapsed since
                             each user's last activity, relative to the input file's
                             modification timestamp (used as the reference time)
  --progress-indicator       Show the 'Tracks — Indicators of Progression' section:
                             median completion stats, max completed, max started,
                             on-track summary, and table of outliers
                             (🚀 ahead / 🏎️💨 behind, outside ± 1 track of the median)
                             Table columns: Status, Name, Completed/Started,
                             Last Completed Track, Inactive For (if --inactive)
  --trimmed-mean             Use trimmed mean (drop bottom/top 10%) instead of median
                             as the reference in the Indicators of Progression section.
                             Also known as Gaussian approach.
  --no-tracks-summary        Hide the Track Summary table
  --no-summary-indicators    Hide the Status icon column (🚀 / ✅ / 🏎️💨) in the
                             per-user Summary table
  --anonymize                Replace names and emails with User1/user1@anon.local etc.
                             Also omits the filename from the report header.

Report title format:
  # Activity Report — YYYY-MM-DD — HH:MM:SS <TZ> [— <date_filter>]

Examples:
    python extract_activity.py participants.csv
    python extract_activity.py participants.csv -o report.md
    python extract_activity.py participants.csv -d 2026-09-01 --summary-only
    python extract_activity.py participants.csv --inactive --progress-indicator -o report.md
    python extract_activity.py participants.csv --anonymize --no-email --no-tracks-summary -o report.md
"""

import argparse
import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# Local timezone for display
LOCAL_TZ = datetime.now().astimezone().tzinfo
LOCAL_TZ_NAME = datetime.now().astimezone().strftime("%Z")


# ── helpers ──────────────────────────────────────────────────────────────────

def fmt_duration(seconds: int) -> str:
    seconds = int(seconds)
    h, m = divmod(seconds // 60, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    elif h:
        return f"{h}h"
    else:
        return f"{m}m"


def utc_to_local(dt_str: str) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S.%f")
        return dt.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return dt_str


def parse_utc(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fmt_inactive(last_act_utc_str: str, file_ts_utc: datetime) -> str:
    last = parse_utc(last_act_utc_str)
    if not last:
        return ""
    return fmt_duration(int((file_ts_utc - last).total_seconds()))


def fmt_date(dt_str: str) -> str:
    return dt_str[:10] if dt_str else ""


def md_table(headers: list, rows: list) -> str:
    if not rows:
        return "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |"
    col_widths = [max(len(h), *(len(str(r[i])) for r in rows))
                  for i, h in enumerate(headers)]
    sep = ["-" * w for w in col_widths]

    def fmt_row(cells):
        return "| " + " | ".join(str(c).ljust(w)
                                  for c, w in zip(cells, col_widths)) + " |"

    lines = [fmt_row(headers), fmt_row(sep)]
    lines += [fmt_row(r) for r in rows]
    return "\n".join(lines)


def progress_icon(completed: int, avg: float) -> str:
    ref = round(avg)
    if completed > ref + 1:
        return "🚀"
    elif completed < ref - 1:
        return "🏎️💨"
    else:
        return "✅"


# ── data loading ─────────────────────────────────────────────────────────────

def load(path: Path, date_filter: str = "") -> dict:
    required = {
        "user_email", "user_display_name", "track_slug",
        "time_spent", "track_completed_at", "last_activity_at",
        "completed_challenges", "total_challenges",
    }

    users: dict = {}

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"Error: missing columns: {missing}")

        for row in reader:
            if date_filter and not row["last_activity_at"].strip().startswith(date_filter):
                continue

            email = row["user_email"].strip()
            if not email:
                continue

            if email not in users:
                users[email] = {
                    "name": row["user_display_name"].strip() or email,
                    "email": email,
                    "total_time": 0,
                    "last_activity_at": "",
                    "tracks": {},
                }

            try:
                users[email]["total_time"] += int(row["time_spent"] or 0)
            except ValueError:
                pass

            last_act = row["last_activity_at"].strip()
            if last_act > users[email]["last_activity_at"]:
                users[email]["last_activity_at"] = last_act

            slug = row["track_slug"].strip()
            if not slug:
                continue

            completed_at = row["track_completed_at"].strip()
            completed = bool(completed_at)
            try:
                done = int(row["completed_challenges"] or 0)
                total = int(row["total_challenges"] or 0)
            except ValueError:
                done, total = 0, 0

            existing = users[email]["tracks"].get(slug)
            if existing is None:
                users[email]["tracks"][slug] = {
                    "completed": completed,
                    "completed_challenges": done,
                    "total_challenges": total,
                    "completed_at": completed_at,
                    "last_activity_at": last_act,
                }
            else:
                if last_act > existing["last_activity_at"]:
                    existing["last_activity_at"] = last_act
                if completed:
                    existing["completed"] = True
                    existing["completed_challenges"] = done
                    existing["total_challenges"] = total
                    if completed_at > existing["completed_at"]:
                        existing["completed_at"] = completed_at
                elif not existing["completed"]:
                    if done > existing["completed_challenges"]:
                        existing["completed_challenges"] = done
                        existing["total_challenges"] = total

    return users


def anonymize_users(users: dict) -> dict:
    """Replace name and email with User1/user1@anon.local etc., sorted by name."""
    anon = {}
    for i, (_, u) in enumerate(
        sorted(users.items(), key=lambda kv: kv[1]["name"].lower()), start=1
    ):
        new_email = f"user{i}@anon.local"
        anon[new_email] = dict(u, name=f"User{i}", email=new_email)
    return anon


def last_completed_track(user: dict) -> str:
    completed = [slug for slug, t in user["tracks"].items() if t["completed"]]
    return max(completed) if completed else "None"


def completed_count(user: dict) -> int:
    return sum(1 for t in user["tracks"].values() if t["completed"])


def started_count(user: dict) -> int:
    return len(user["tracks"])


# ── report sections ──────────────────────────────────────────────────────────

def section_progress_indicator(users: dict, tracks_avg: float,
                                file_ts_utc: datetime = None,
                                method_label: str = "Median") -> str:
    total = len(users)
    avg_rounded = round(tracks_avg)
    lo, hi = avg_rounded - 1, avg_rounded + 1

    max_completed = max(completed_count(u) for u in users.values())
    max_started   = max(started_count(u)   for u in users.values())

    def count_at(n):
        return sum(1 for u in users.values() if completed_count(u) == n)

    def pct(n):
        c = count_at(n)
        return f"{c / total * 100:.0f}% ({c}/{total})", c

    at_pct, _  = pct(avg_rounded)
    lo_pct, _  = pct(lo)
    hi_pct, _  = pct(hi)

    on_track_c = sum(1 for u in users.values() if lo <= completed_count(u) <= hi)
    on_track_pct = f"{on_track_c / total * 100:.0f}%"

    lines = [
        "## Tracks — Indicators of Progression\n",
        f"{method_label} tracks completed: **{avg_rounded}**",
        f"> Max tracks completed: **{max_completed}**",
        f"> Max tracks started: **{max_started}**\n",
        f"### ✅ **{on_track_pct}** ({on_track_c}/{total}) participants have completed {lo}-{hi} tracks\n",
        f"> - ✅ {hi_pct} participants have completed {hi} tracks.",
        f"> - ✅ {at_pct} participants have completed {avg_rounded} tracks.",
        f"> - ✅ {lo_pct} participants have completed {lo} tracks.\n",
    ]

    # Table: only users OUTSIDE the tolerance zone [avg-1, avg+1]
    headers = ["Status", "Name", "Completed/Started", "Last Completed Track"]
    if file_ts_utc:
        headers.append("Inactive For")

    rows = []
    sorted_users = sorted(
        users.values(),
        key=lambda u: (-completed_count(u), u["name"].lower())
    )
    for u in sorted_users:
        count = completed_count(u)
        if lo <= count <= hi:
            continue  # within tolerance — skip
        icon = "🚀" if count > hi else "🏎️💨"
        row = [icon, u["name"], f"{count}/*{started_count(u)}*", last_completed_track(u)]
        if file_ts_utc:
            row.append(fmt_inactive(u["last_activity_at"], file_ts_utc))
        rows.append(row)

    if rows:
        lines.append(md_table(headers, rows))
    else:
        lines.append("_All participants are within one track of the reference._")

    return "\n".join(lines) + "\n"


def section_track_summary(users: dict) -> str:
    total_users = len(users)
    track_completions: dict = {}
    for u in users.values():
        for slug, t in u["tracks"].items():
            if slug not in track_completions:
                track_completions[slug] = 0
            if t["completed"]:
                track_completions[slug] += 1

    rows = []
    for i, slug in enumerate(sorted(track_completions), start=1):
        count = track_completions[slug]
        pct = f"{count / total_users * 100:.0f}%"
        rows.append([str(i), slug, str(count), pct])

    return f"## Track Summary\n\n{md_table(['#', 'Track', 'Completed By', '% of Students'], rows)}\n"


def section_summary(users: dict, show_email: bool = True,
                    file_ts_utc: datetime = None,
                    tracks_avg: float = None,
                    show_indicators: bool = False,
                    ts_label: str = "") -> str:
    headers = ["#", "Name"]
    if show_email:
        headers.append("Email")
    if show_indicators and tracks_avg is not None:
        headers.append("Status")
    headers += ["# Completed/Started", "Last Completed", "Total Time Spent", "Last Seen"]
    if file_ts_utc:
        headers.append("Inactive For")

    rows = []
    for i, u in enumerate(sorted(users.values(), key=lambda x: x["name"].lower()), start=1):
        count = completed_count(u)
        row = [str(i), u["name"]]
        if show_email:
            row.append(u["email"])
        if show_indicators and tracks_avg is not None:
            row.append(progress_icon(count, round(tracks_avg)))
        row += [
            f"{count}/*{started_count(u)}*",
            last_completed_track(u),
            fmt_duration(u["total_time"]),
            utc_to_local(u["last_activity_at"]),
        ]
        if file_ts_utc:
            row.append(fmt_inactive(u["last_activity_at"], file_ts_utc))
        rows.append(row)

    heading = f"## Summary — {ts_label}" if ts_label else "## Summary"
    return f"{heading}\n\n{md_table(headers, rows)}\n"


def section_per_user(users: dict, show_email: bool = True) -> str:
    blocks = []
    for u in sorted(users.values(), key=lambda x: x["name"].lower()):
        heading = (f"### {u['name']} ({u['email']})\n" if show_email
                   else f"### {u['name']}\n")
        comp = completed_count(u)
        started = started_count(u)
        user_last_seen = utc_to_local(u["last_activity_at"])
        totals = f"Completed/Started: **{comp}/{started}** — Last Seen: **{user_last_seen}**\n"
        rows = []
        for i, slug in enumerate(sorted(u["tracks"]), start=1):
            t = u["tracks"][slug]
            status = "✅ Completed" if t["completed"] else "⬜ In Progress"
            progress = f"{t['completed_challenges']} / {t['total_challenges']}"
            track_last_seen = utc_to_local(t["last_activity_at"])
            if t["last_activity_at"] == u["last_activity_at"]:
                track_last_seen = f"**{track_last_seen}**"
            rows.append([str(i), slug, status, progress, track_last_seen])

        blocks.append(heading + "\n" + totals + "\n" + md_table(["#", "Track", "Status", "Challenges", "Last Seen"], rows))

    return "## Per-User Track Detail\n\n" + "\n\n".join(blocks) + "\n"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a user activity report from a participant CSV.")
    parser.add_argument("input", type=Path, help="Input CSV file")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output file (default: stdout)")
    parser.add_argument("--no-email", action="store_true",
                        help="Omit email addresses from the report")
    parser.add_argument("--summary-only", action="store_true",
                        help="Output part 1 (summary) only")
    parser.add_argument("-d", "--date", default="",
                        help="Filter by date (YYYY-MM-DD, based on last_activity_at)")
    parser.add_argument("--inactive", action="store_true",
                        help="Show 'Inactive For' column (relative to file modification time)")
    parser.add_argument("--progress-indicator", action="store_true",
                        help="Show 'Tracks — Indicators of Progression' section")
    parser.add_argument("--trimmed-mean", action="store_true",
                        help="Use trimmed mean (drop top/bottom 10%%) instead of median as reference")
    parser.add_argument("--no-tracks-summary", action="store_true",
                        help="Hide the Track Summary table")
    parser.add_argument("--no-summary-indicators", action="store_true",
                        help="Hide the Status icon column in the Summary table")
    parser.add_argument("--anonymize", action="store_true",
                        help="Replace names and emails with User1/user1@anon.local etc.")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Error: file not found: {args.input}")

    # File modification timestamp as UTC reference
    current_file_timestamp = datetime.fromtimestamp(
        args.input.stat().st_mtime, tz=timezone.utc)
    file_ts_local = current_file_timestamp.astimezone(LOCAL_TZ)
    file_ts_date  = file_ts_local.strftime("%Y-%m-%d")
    file_ts_time  = file_ts_local.strftime("%H:%M:%S")
    file_ts_label = f"{file_ts_date} — {file_ts_time}"

    users = load(args.input, date_filter=args.date)
    if not users:
        sys.exit(f"No data found{' for ' + args.date if args.date else ''}.")
    if args.anonymize:
        users = anonymize_users(users)

    show_email = not args.no_email
    file_ts_utc = current_file_timestamp if args.inactive else None

    # Reference: median (default) or trimmed mean (--trimmed-mean)
    counts = sorted(completed_count(u) for u in users.values())
    if args.trimmed_mean:
        k = max(1, len(counts) // 10)
        tracks_avg = sum(counts[k:-k]) / len(counts[k:-k])
        method_label = "Trimmed-mean"
    else:
        tracks_avg = statistics.median(counts)
        method_label = "Median"
    show_indicators = not args.no_summary_indicators

    date_label = f" — {args.date}" if args.date else ""
    file_info = "" if args.anonymize else f"File: {args.input.name} — "
    parts = [
        f"# Activity Report — {file_ts_label} {LOCAL_TZ_NAME}{date_label}\n",
        f"_{file_info}last modified {file_ts_label} {LOCAL_TZ_NAME} · Timestamps in {LOCAL_TZ_NAME} (source: UTC)_\n",
    ]

    if args.progress_indicator:
        parts.append(section_progress_indicator(users, tracks_avg, file_ts_utc, method_label))

    if not args.no_tracks_summary:
        parts.append(section_track_summary(users))

    parts.append(section_summary(
        users, show_email, file_ts_utc,
        tracks_avg=tracks_avg,
        show_indicators=show_indicators,
        ts_label=f"{file_ts_label} {LOCAL_TZ_NAME}",
    ))

    if not args.summary_only:
        parts.append(section_per_user(users, show_email))

    report = "\n".join(parts)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
