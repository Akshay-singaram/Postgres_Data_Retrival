"""
CSV export with optional chunking for large DataFrames.
"""

import gc
import os
from datetime import datetime

import pandas as pd

CHUNK_THRESHOLD = 500_000  # rows — above this we write in chunks
CHUNK_SIZE = 100_000


def _generate_filename(start_time: datetime, end_time: datetime) -> str:
    st = start_time.strftime("%Y%m%d_%H%M")
    et = end_time.strftime("%Y%m%d_%H%M")
    return f"WINCCOA_DATA_{st}to{et}.csv"


def export_to_csv(
    df: pd.DataFrame,
    output_dir: str,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """Write the DataFrame to a CSV file.

    Returns the full path of the created file.
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    filename = _generate_filename(start_time, end_time)
    path = os.path.join(output_dir, filename)

    row_count = len(df)

    if row_count <= CHUNK_THRESHOLD:
        df.to_csv(path, index=True)
    else:
        # Write in chunks to manage memory
        first_chunk = True
        for start_idx in range(0, row_count, CHUNK_SIZE):
            chunk = df.iloc[start_idx : start_idx + CHUNK_SIZE]
            if first_chunk:
                chunk.to_csv(path, index=True, mode="w")
                first_chunk = False
            else:
                chunk.to_csv(path, index=True, mode="a", header=False)
            del chunk
            gc.collect()

    file_size = os.path.getsize(path)
    size_mb = file_size / (1024 * 1024)
    print(f"[exporter] Exported {row_count} rows x {len(df.columns)} columns "
          f"-> {path}  ({size_mb:.2f} MB)")

    return path
