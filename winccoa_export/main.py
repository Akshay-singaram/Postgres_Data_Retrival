"""
WinCC OA Historian Data Export — main entry point.

Edit the configuration section below, then run:
    python main.py
"""

import time
from datetime import datetime

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


def main():
    t_total = time.time()

    start_dt = _parse(START_TIME)
    end_dt = _parse(END_TIME)
    start_ns = _datetime_to_ns(start_dt)

    print(f"=== WinCC OA Data Export ===")
    print(f"    Range : {start_dt}  ->  {end_dt}")
    print(f"    Rate  : {SAMPLE_RATE}")
    print()

    # ---- 1. Connect --------------------------------------------------
    t0 = time.time()
    conn = get_connection()
    print(f"[main] Connected to database  ({time.time() - t0:.2f}s)")

    try:
        # ---- 2. Segment lookup ---------------------------------------
        t0 = time.time()
        segments = get_segments_for_range(conn, start_dt, end_dt)
        print(f"[main] Segment lookup  ({time.time() - t0:.2f}s)")

        if not segments:
            print("[main] No segments found for the requested range. Exiting.")
            return

        segment_ids = [s["segment_id"] for s in segments]

        # ---- 3. Element discovery ------------------------------------
        t0 = time.time()
        elements_df = get_elements_in_segments(conn, segment_ids)
        print(f"[main] Discovered {len(elements_df)} elements  "
              f"({time.time() - t0:.2f}s)")

        if elements_df.empty:
            print("[main] No elements found in the matched segments. Exiting.")
            return

        element_map = dict(
            zip(elements_df["element_id"], elements_df["element_name"])
        )
        element_ids = list(element_map.keys())

        # ---- 4. Last-known values (look-back) ------------------------
        t0 = time.time()
        # For the look-back we also include segments that end before our window
        lookback_segments = get_segments_for_range(
            conn,
            datetime(1970, 1, 1),
            end_dt,
        )
        lookback_ids = [s["segment_id"] for s in lookback_segments]

        last_values_by_id = get_last_known_values(
            conn, lookback_ids, start_ns, element_ids
        )
        # Convert keys from element_id to element_name for resample_and_fill
        initial_values = {
            element_map[eid]: val
            for eid, val in last_values_by_id.items()
            if eid in element_map
        }
        print(f"[main] Look-back complete  ({time.time() - t0:.2f}s)")

        # ---- 5 & 6. Extract raw data from each segment & combine -----
        t0 = time.time()
        import pandas as pd

        raw_frames = []
        for seg in segments:
            sid = seg["segment_id"]
            seg_start = max(seg["start_time"], start_ns)
            seg_end = min(seg["end_time"], _datetime_to_ns(end_dt))
            df_seg = extract_segment_data(conn, sid, seg_start, seg_end)
            if not df_seg.empty:
                raw_frames.append(df_seg)
            print(f"       segment {sid}: {len(df_seg)} rows")

        if raw_frames:
            raw_df = pd.concat(raw_frames, ignore_index=True)
        else:
            raw_df = pd.DataFrame(columns=["timestamp", "element_id", "value"])

        del raw_frames
        print(f"[main] Extracted {len(raw_df)} total raw rows  "
              f"({time.time() - t0:.2f}s)")

        # ---- 7. Pivot ------------------------------------------------
        t0 = time.time()
        pivoted = pivot_data(raw_df, element_map)
        del raw_df
        print(f"[main] Pivoted shape: {pivoted.shape}  "
              f"({time.time() - t0:.2f}s)")

        # ---- 8. Resample & forward-fill ------------------------------
        t0 = time.time()
        result = resample_and_fill(
            pivoted, start_dt, end_dt, SAMPLE_RATE, initial_values
        )
        del pivoted
        print(f"[main] Resampled shape: {result.shape}  "
              f"({time.time() - t0:.2f}s)")

        nan_count = result.isna().sum().sum()
        print(f"[main] NaN values remaining after forward-fill: {nan_count}")

        # ---- 9. Export -----------------------------------------------
        t0 = time.time()
        out_path = export_to_csv(result, OUTPUT_DIR, start_dt, end_dt)
        print(f"[main] CSV export  ({time.time() - t0:.2f}s)")

        # ---- 10. Summary ---------------------------------------------
        print()
        print(f"=== Done in {time.time() - t_total:.2f}s ===")
        print(f"    Output : {out_path}")
        print(f"    Rows   : {len(result)}")
        print(f"    Columns: {len(result.columns)}")

    finally:
        conn.close()
        print("[main] Database connection closed.")


if __name__ == "__main__":
    main()
