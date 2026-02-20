# WinCC OA Historian Data Export

A Python toolkit for extracting historical process data from a **WinCC OA PostgreSQL historian** database and exporting it as a clean, resampled CSV file.

Comes with both a **command-line interface** and a **graphical interface** (Tkinter) that includes date/time pickers and a real-time progress bar.

---

## Features

- **GUI mode** (`gui.py`) — visual date/time pickers, sample-rate selector, output-directory browser, and a live progress bar that shows exactly how far the extraction has progressed.
- **CLI mode** (`main.py`) — headless execution with configuration constants at the top of the file; prints progress percentages to the console.
- **Segment-aware** — automatically discovers which WinCC OA historian event-table segments overlap your requested time range.
- **Look-back / forward-fill** — retrieves the last known value for every element *before* the start time so there are no gaps at the beginning of the output.
- **Configurable sample rate** — resample to any Pandas frequency string (`1s`, `5s`, `1min`, `15min`, …).
- **Large-file friendly** — CSV export automatically switches to chunked writing when the row count exceeds 500 000 to keep memory usage low.

---

## Project Structure

```
winccoa_export/
├── gui.py              # Tkinter GUI entry point (date/time pickers + progress bar)
├── main.py             # CLI entry point & shared pipeline function (run_pipeline)
├── db_config.py        # PostgreSQL connection settings
├── segment_lookup.py   # Finds historian segments that overlap the requested range
├── data_extract.py     # Reads raw event rows from segment tables
├── data_process.py     # Pivots raw data and resamples to a uniform time grid
├── exporter.py         # Writes the final DataFrame to CSV
└── requirements.txt    # Python dependencies
```

### Module Responsibilities

| Module | Purpose |
|---|---|
| **gui.py** | Tkinter window with `tkcalendar.DateEntry` and `tktimepicker.SpinTimePickerOld` for choosing start/end times, a `ttk.Combobox` for the sample rate, a directory browser, and a `ttk.Progressbar`. Runs the pipeline in a background thread so the UI stays responsive. |
| **main.py** | Exposes `run_pipeline(start_dt, end_dt, sample_rate, output_dir, on_progress=None)` which orchestrates the full extraction. Also serves as a standalone CLI entry point with hard-coded configuration constants. |
| **db_config.py** | Stores the `DB_CONFIG` dict (host, port, database, user, password) and provides `get_connection()`. |
| **segment_lookup.py** | Queries the `segments` table to find event-table segments whose time range overlaps the requested window. Filters by readable status codes. |
| **data_extract.py** | Queries individual `._event_{segment_id}_a` tables for raw `(timestamp, element_id, value)` rows. Also performs per-element look-back to find the last known value before the window. |
| **data_process.py** | `pivot_data()` converts long-form rows into a wide DataFrame (one column per element). `resample_and_fill()` builds a uniform `DatetimeIndex`, injects seed values, and forward-fills. |
| **exporter.py** | Writes the final DataFrame to a timestamped CSV. Uses chunked writing for DataFrames larger than 500 000 rows. |

---

## Prerequisites

- **Python 3.10+**
- A running **PostgreSQL** instance with the WinCC OA historian schema (tables: `segments`, `elements`, `._event_*_a`).
- **Tkinter** (ships with most Python installations; on Linux you may need `sudo apt install python3-tk`).

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Akshay-singaram/Postgres_Data_Retrival.git
cd Postgres_Data_Retrival/winccoa_export

# 2. (Recommended) Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Edit `db_config.py` to match your PostgreSQL connection:

```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "postgres",       # your WinCC OA database name
    "user": "postgres",
    "password": "changeme",       # your actual password
}
```

---

## Usage

### GUI mode (recommended)

```bash
python gui.py
```

1. **Set the start date and time** using the calendar picker and the hour/minute spinners.
2. **Set the end date and time** the same way.
3. **Choose a sample rate** from the dropdown (`1s`, `5s`, `10s`, `30s`, `1min`, `5min`, `15min`).
4. **Pick an output directory** with the *Browse* button (or type the path).
5. Click **"Export data to CSV"**.

The **progress bar** fills in real time as the pipeline executes:

| Progress | Stage |
|---|---|
| 0 – 5 % | Connecting to the database |
| 5 – 15 % | Segment lookup, element discovery, look-back for initial values |
| 20 – 75 % | Extracting raw data segment by segment (bar advances per segment) |
| 75 – 85 % | Pivoting raw data into wide format |
| 85 – 92 % | Resampling to the uniform time grid and forward-filling |
| 92 – 100 % | Writing the CSV file |

A success dialog shows the output path when finished; an error dialog appears if anything goes wrong.

### CLI mode

Edit the constants at the top of `main.py`:

```python
START_TIME  = "2025-01-01 00:00:00"
END_TIME    = "2025-01-01 01:00:00"
SAMPLE_RATE = "1s"
OUTPUT_DIR  = r"C:\Users\ISBL Admin\Downloads"
```

Then run:

```bash
python main.py
```

Progress is printed to the console as percentage messages.

---

## Output

The exported CSV is named automatically based on the time range:

```
WINCCOA_DATA_20250101_0000to20250101_0100.csv
```

- **Index column**: `timestamp` (uniform grid at the chosen sample rate).
- **Data columns**: one per discovered WinCC OA element, named by `element_name`.
- Values are forward-filled so every cell has a value (unless no data existed before the window for that element).

---

## Dependencies

| Package | Purpose |
|---|---|
| `psycopg2-binary` | PostgreSQL driver |
| `pandas` | Data manipulation, resampling, CSV export |
| `tkcalendar` | Calendar date-picker widget for the GUI |
| `tktimepicker` | Hour/minute spinner widget for the GUI |

All listed in `requirements.txt`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'tkinter'` | Install the Tk package for your OS: `sudo apt install python3-tk` (Debian/Ubuntu) or reinstall Python with Tk support. |
| `psycopg2.OperationalError: could not connect` | Check `db_config.py` — verify host, port, database name, user, and password. Make sure the PostgreSQL server is running and accepting connections. |
| `No segments found for the requested time range` | The historian has no data segments that overlap your chosen start/end window. Widen the range or verify that data exists in the database. |
| Progress bar stuck at a low percentage | The look-back step (finding initial values) can be slow if there are many elements and many historical segments. This is normal for large historians. |
