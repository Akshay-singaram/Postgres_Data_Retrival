"""
WinCC OA Historian Data Export — main entry point.

Can be run directly (CLI mode) or imported by gui.py which calls
run_pipeline() with a progress callback.

    python main.py          # CLI
    python gui.py           # GUI with progress bar
"""

import time
from datetime import datetime, timezone

import pandas as pd

from db_config import get_connection
from segment_lookup import get_segments_for_range, _datetime_to_ns
from data_extract import (
    get_elements_in_segments,
    extract_segment_data,
    get_last_known_values,
)
from data_process import pivot_data, resample_and_fill
from exporter import export_to_csv

# ========================== USER CONFIGURATION ==========================
START_TIME = "2025-01-01 00:00:00"
END_TIME = "2025-01-01 01:00:00"
SAMPLE_RATE = "1s"                          # pandas freq string
OUTPUT_DIR = r"C:\Users\ISBL Admin\Downloads"
# ========================================================================


def _parse(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")


def run_pipeline(
    start_dt: datetime,
    end_dt: datetime,
    sample_rate: str,
    output_dir: str,
    on_progress=None,
) -> str:
    """Execute the full export pipeline.

    Parameters
    ----------
    start_dt, end_dt : datetime boundaries for the export.
    sample_rate : pandas frequency string ('1s', '5s', '1min', …).
    output_dir : directory where the CSV will be written.
    on_progress : optional callback(percent: int, message: str)
        called at each stage so a GUI can update a progress bar.

    Returns
    -------
    The file path of the exported CSV, or an error message string
    prefixed with "ERROR: ".
    """
    def _progress(pct: int, msg: str):
        print(f"[{pct:3d}%] {msg}")
        if on_progress:
            on_progress(pct, msg)

    t_total = time.time()
    start_ns = _datetime_to_ns(start_dt)
    end_ns = _datetime_to_ns(end_dt)

    _progress(0, "Connecting to database…")

    # ---- 1. Connect --------------------------------------------------
    try:
        conn = get_connection()
    except Exception as e:
        return f"ERROR: Database connection failed — {e}"

    try:
        # ---- 2. Segment lookup ---------------------------------------
        _progress(5, "Looking up segments…")
        segments = get_segments_for_range(conn, start_dt, end_dt)

        if not segments:
            return "ERROR: No segments found for the requested time range."

        segment_ids = [s["segment_id"] for s in segments]
        num_segments = len(segments)

        # ---- 3. Element discovery ------------------------------------
        _progress(10, f"Discovering elements across {num_segments} segment(s)…")
        elements_df = get_elements_in_segments(conn, segment_ids)

        if elements_df.empty:
            return "ERROR: No elements found in matched segments."

        element_map = dict(
            zip(elements_df["element_id"], elements_df["element_name"])
        )
        element_ids = list(element_map.keys())

        # ---- 4. Last-known values (look-back) ------------------------
        _progress(15, f"Looking back for initial values ({len(element_ids)} elements)…")
        lookback_segments = get_segments_for_range(
            conn, datetime(1970, 1, 1, tzinfo=timezone.utc), end_dt,
        )
        lookback_ids = [s["segment_id"] for s in lookback_segments]

        last_values_by_id = get_last_known_values(
            conn, lookback_ids, start_ns, element_ids
        )
        initial_values = {
            element_map[eid]: val
            for eid, val in last_values_by_id.items()
            if eid in element_map
        }

        # ---- 5 & 6. Extract raw data per segment --------------------
        # Progress 20% → 75% is split across segments
        raw_frames = []
        for idx, seg in enumerate(segments):
            pct = 20 + int((idx / num_segments) * 55)
            sid = seg["segment_id"]
            _progress(pct, f"Extracting segment {idx + 1}/{num_segments} "
                           f"(id {sid})…")

            seg_start = max(seg["start_time"], start_ns)
            seg_end = min(seg["end_time"], end_ns)
            df_seg = extract_segment_data(conn, sid, seg_start, seg_end)
            if not df_seg.empty:
                raw_frames.append(df_seg)

        if raw_frames:
            raw_df = pd.concat(raw_frames, ignore_index=True)
        else:
            raw_df = pd.DataFrame(columns=["timestamp", "element_id", "value"])
        del raw_frames

        total_raw = len(raw_df)
        _progress(75, f"Extracted {total_raw} raw rows. Pivoting…")

        # ---- 7. Pivot ------------------------------------------------
        pivoted = pivot_data(raw_df, element_map)
        del raw_df

        # ---- 8. Resample & forward-fill ------------------------------
        _progress(85, f"Resampling at {sample_rate} and forward-filling…")
        result = resample_and_fill(
            pivoted, start_dt, end_dt, sample_rate, initial_values
        )
        del pivoted

        # ---- 9. Export -----------------------------------------------
        _progress(92, f"Exporting CSV ({len(result)} rows × "
                       f"{len(result.columns)} cols)…")
        out_path = export_to_csv(result, output_dir, start_dt, end_dt)

        elapsed = time.time() - t_total
        _progress(100, f"Done in {elapsed:.1f}s — {out_path}")
        return out_path

    finally:
        conn.close()
        print("[main] Database connection closed.")


# --------------------- CLI entry point --------------------------------
def main():
    start_dt = _parse(START_TIME)
    end_dt = _parse(END_TIME)

    print(f"=== WinCC OA Data Export ===")
    print(f"    Range : {start_dt}  ->  {end_dt}")
    print(f"    Rate  : {SAMPLE_RATE}")
    print()

    result = run_pipeline(start_dt, end_dt, SAMPLE_RATE, OUTPUT_DIR)

    if result.startswith("ERROR:"):
        print(result)
    else:
        print(f"\nExported to: {result}")


if __name__ == "__main__":
    main()
