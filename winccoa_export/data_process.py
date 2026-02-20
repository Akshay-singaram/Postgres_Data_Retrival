"""
Data processing — pivot raw event data, resample to a uniform grid,
and forward-fill gaps.
"""

from datetime import datetime, timedelta

import pandas as pd


def pivot_data(
    raw_df: pd.DataFrame,
    element_map: dict,
) -> pd.DataFrame:
    """Pivot long-form data into wide form (timestamps x element names).

    Parameters
    ----------
    raw_df : DataFrame with columns [timestamp, element_id, value]
    element_map : {element_id: element_name}

    Returns
    -------
    Pivoted DataFrame indexed by timestamp, one column per element_name.
    """
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df["element_name"] = df["element_id"].map(element_map)
    # Drop rows whose element_id wasn't in the map (shouldn't happen, but safe)
    df.dropna(subset=["element_name"], inplace=True)

    pivoted = df.pivot_table(
        index="timestamp",
        columns="element_name",
        values="value",
        aggfunc="last",
    )
    return pivoted


def resample_and_fill(
    pivoted_df: pd.DataFrame,
    start_time: datetime,
    end_time: datetime,
    sample_rate: str = "1s",
    initial_values: dict | None = None,
) -> pd.DataFrame:
    """Resample to a uniform time grid and forward-fill.

    Parameters
    ----------
    pivoted_df : Output of pivot_data (timestamps x element names).
    start_time, end_time : Bounds of the desired output.
    sample_rate : Pandas frequency string ('1s', '5s', '1min', etc.).
    initial_values : {element_name: value} — seeded before the first
        real data point so forward-fill has something to propagate.

    Returns
    -------
    DataFrame on a uniform DatetimeIndex with no gaps.
    """
    if pivoted_df.empty:
        print("[data_process] Warning: pivoted DataFrame is empty, "
              "returning empty result.")
        return pd.DataFrame()

    # Build the uniform time index
    time_index = pd.date_range(start=start_time, end=end_time, freq=sample_rate)

    # Inject initial (look-back) values just before the window so ffill
    # can pick them up.
    if initial_values:
        seed_time = start_time - timedelta(microseconds=1)
        seed_row = pd.DataFrame(
            {col: [initial_values.get(col)] for col in pivoted_df.columns},
            index=pd.DatetimeIndex([seed_time]),
        )
        pivoted_df = pd.concat([seed_row, pivoted_df])

    # Reindex to the uniform grid (new timestamps become NaN)
    pivoted_df = pivoted_df.reindex(
        pivoted_df.index.union(time_index)
    )

    # Forward-fill, then keep only the uniform grid rows
    pivoted_df = pivoted_df.ffill()
    pivoted_df = pivoted_df.reindex(time_index)

    pivoted_df.index.name = "timestamp"
    return pivoted_df
