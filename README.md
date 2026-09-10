# `extract_activity.py`
_Sept 2026_

Reads the Download CSV file exported from the [Instruqt Activity Dashboard](https://docs.instruqt.com/reporting/activity-report) to produces a two-part Markdown report.

> All timestamps in the source CSV are UTC. The report converts them to the local machine timezone automatically and labels them accordingly.

> NOTE: this code has been done by Claude AI.

### Input

A CSV file exported from the Instruqt **Activity Report** page. Each row represents one track attempt per user (the same user may appear multiple times for the same track due to retries).

### Report structure

**Part 1 — Summary**
- *(optional)* Tracks — Indicators of Progression
- *(optional)* Track Summary table (completion rates per track)
- Per-user Summary table

**Part 2 — Per-user track detail**
- One section per user listing unique tracks, completion status, and challenge progress

**Report title**
The title always includes the file modification timestamp as the reference time:
```
# Activity Report — 2026-09-08T09:55:36 CEST
# Activity Report — 2026-09-08T09:55:36 CEST — 2026-09-01   (with -d filter)
```

### Usage

```bash
python extract_activity.py input.csv                        # stdout, all sections
python extract_activity.py input.csv -o report.md           # write to file
python extract_activity.py input.csv -d 2026-09-01          # filter by date
python extract_activity.py input.csv --summary-only         # part 1 only
python extract_activity.py input.csv --inactive --progress-indicator -o report.md
python extract_activity.py input.csv --anonymize --no-email -o report.md
```
Example: [sample](./sample.md)

### Options

| Option | Description |
|---|---|
| `input` | Input CSV file (Instruqt participant export) |
| `-o, --output FILE` | Write report to FILE instead of stdout |
| `-d, --date YYYY-MM-DD` | Filter rows to a specific date (based on `last_activity_at`) |
| `--summary-only` | Output Part 1 only — skip per-user track detail |
| `--no-email` | Omit the Email column from all tables |
| `--inactive` | Add an **Inactive For** column — time elapsed since each user's last activity, relative to the input file's modification timestamp |
| `--progress-indicator` | Show the **Tracks — Indicators of Progression** section with average completion stats and a table of outliers (🚀 ahead / 🏎️💨 behind, ±1 track of the average). Table columns: Status, Name, Completed, Last Completed Track, Inactive For (if `--inactive`) |
| `--no-tracks-summary` | Hide the Track Summary table |
| `--no-summary-indicators` | Hide the Status icon column (🚀 / ✅ / 🏎️💨) in the Summary table |
| `--anonymize` | Replace real names and emails with `User1`, `user1@anon.local`, etc. Also omits the filename from the report header. |

### Status icons

| Icon | Meaning |
|---|---|
| 🚀 | Ahead — completed more than average + 1 track |
| ✅ | On track — within ±1 track of the average |
| 🏎️💨 | Behind — completed fewer than average − 1 track |

### Required CSV columns

Standard Instruqt participant export columns used by the script:

`user_email`, `user_display_name`, `track_slug`, `time_spent`, `track_completed_at`, `last_activity_at`, `completed_challenges`, `total_challenges`

---
