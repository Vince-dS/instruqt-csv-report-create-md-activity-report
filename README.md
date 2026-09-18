# `extract_activity.py`
_Sept 2026_

Reads the Download CSV file exported from the [Instruqt Activity Dashboard](https://docs.instruqt.com/reporting/activity-report) to produce a two-part Markdown report.

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
- One section per user with a `Completed/Started` and `Last Seen` header line, followed by a numbered table of unique tracks with completion status, challenge progress, and per-track Last Seen (the matching row is bolded)

**Report title**
The title always includes the file modification timestamp as the reference time:
```
# Activity Report — 2026-09-08 — 09:55:36 CEST
# Activity Report — 2026-09-08 — 09:55:36 CEST — 2026-09-01   (with -d filter)
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
| `--progress-indicator` | Show the **Tracks — Indicators of Progression** section: median tracks completed, max completed, max started, on-track summary (±1 of median), and a table of outliers (🚀 ahead / 🏎️💨 behind). Table columns: Status, Name, Completed/Started, Last Completed Track, Inactive For (if `--inactive`) |
| `--trimmed-mean` | Use trimmed mean (drop bottom/top 10%) instead of median as the reference in the Indicators of Progression section |
| `--no-tracks-summary` | Hide the Track Summary table |
| `--no-summary-indicators` | Hide the Status icon column (🚀 / ✅ / 🏎️💨) in the Summary table |
| `--anonymize` | Replace real names and emails with `User1`, `user1@anon.local`, etc. Also omits the filename from the report header. |

### Summary table columns

`#` | `Name` | `Email` | `Status` | `# Completed/Started` | `Last Completed` | `Total Time Spent` | `Last Seen` | `Inactive For`

(`Email` hidden with `--no-email`, `Status` hidden with `--no-summary-indicators`, `Inactive For` shown with `--inactive`)

### Status icons

| Icon | Meaning |
|---|---|
| 🚀 | Ahead — completed more than reference + 1 track |
| ✅ | On track — within ±1 track of the reference |
| 🏎️💨 | Behind — completed fewer than reference − 1 track |

### Required CSV columns

Standard Instruqt participant export columns used by the script:

`user_email`, `user_display_name`, `track_slug`, `time_spent`, `track_completed_at`, `last_activity_at`, `completed_challenges`, `total_challenges`

---

### Changelog

**2026-09-18**
- Part 2 per-user sections now show `Completed/Started: **X/Y** — Last Seen: **timestamp**` header line; the track row matching the user's Last Seen is bolded in the table
- Part 2 track table now has a row number (`#`) column and a `Last Seen` column per track
- Summary table: new column order — Status moved next to Name; `# Completed/Started` replaces separate columns; `Last Completed` shortened label
- Report title timestamp format changed from `2026-09-08T09:55:36 CEST` to `2026-09-08 — 09:55:36 CEST`; Summary table heading includes the same date/time

**2026-09-10**
- Default progression reference switched from arithmetic mean to **median** (robust against outliers)
- New `--trimmed-mean` option: drops bottom/top 10% before averaging
- Status tolerance zone widened to ±1 track of the reference (median−1 to median+1 all show ✅)
- `Last Completed Track` now uses alphabetical-max of completed slugs (maps to curriculum position) instead of most-recent-by-timestamp
- Indicators of Progression section: new layout with max completed, max started, on-track percentage breakdown, and `Completed/Started` column in the outlier table
