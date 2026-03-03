"""
Raw data extraction from WinCC OA event tables.

Event tables are named  "_event_{segment_id}_a".
Table names cannot be parameterised in SQL, so we use psycopg2.sql to
build them safely.  segment_id always comes from our own segments query
(never from user input), but we still validate it as an integer.
"""

from datetime import datetime

import pandas as pd
from psycopg2 import sql


# ------------------------------------------------------------------ helpers
def _datetime_to_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def _event_table_name(segment_id: int) -> str:
    """Return the literal table name."""
    return f"_event_{int(segment_id)}_a"


# --------------------------------------------------- element discovery
def get_all_elements(conn) -> pd.DataFrame:
    """Return every element (element_id, element_name, type_)."""
    with conn.cursor() as cur:
        cur.execute("SELECT element_id, element_name, type_ FROM elements;")
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


def get_elements_in_segments(conn, segment_ids: list) -> pd.DataFrame:
    """Discover which elements actually have data in the given segments.

    Returns a DataFrame with columns: element_id, element_name, type_
    """
    all_element_ids: set[int] = set()

    for sid in segment_ids:
        table = _event_table_name(sid)
        q = sql.SQL("SELECT DISTINCT element_id FROM {} LIMIT 1000").format(
            sql.Identifier(table)
        )
        try:
            with conn.cursor() as cur:
                cur.execute(q)
                rows = cur.fetchall()
            all_element_ids.update(r[0] for r in rows)
        except Exception as e:
            print(f"[data_extract] Skipping segment {sid} during element "
                  f"discovery (table may not exist): {e}")
            conn.rollback()

    if not all_element_ids:
        return pd.DataFrame(columns=["element_id", "element_name", "type_"])

    placeholders = ",".join(["%s"] * len(all_element_ids))
    query = (
        f"SELECT element_id, element_name, type_ "
        f"FROM elements WHERE element_id IN ({placeholders})"
    )
    with conn.cursor() as cur:
        cur.execute(query, list(all_element_ids))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


# ------------------------------------------------- raw data extraction
def extract_segment_data(
    conn,
    segment_id: int,
    start_ns: int,
    end_ns: int,
) -> pd.DataFrame:
    """Extract rows from a single event table for [start_ns, end_ns).

    Returns DataFrame with columns: [timestamp, element_id, value]
    """
    table = _event_table_name(segment_id)
    q = sql.SQL(
        "SELECT element_id, ts, "
        "COALESCE(value_number::text, value_string) AS value "
        "FROM {} "
        "WHERE ts >= %s AND ts < %s "
        "ORDER BY ts"
    ).format(sql.Identifier(table))

    try:
        with conn.cursor() as cur:
            cur.execute(q, (start_ns, end_ns))
            rows = cur.fetchall()
    except Exception as e:
        print(f"[data_extract] Error reading segment {segment_id}: {e}")
        conn.rollback()
        return pd.DataFrame(columns=["timestamp", "element_id", "value"])

    if not rows:
        return pd.DataFrame(columns=["timestamp", "element_id", "value"])

    df = pd.DataFrame(rows, columns=["element_id", "ts_ns", "value"])
    df["timestamp"] = pd.to_datetime(df["ts_ns"], unit="ns", utc=True)
    df.drop(columns=["ts_ns"], inplace=True)
    return df[["timestamp", "element_id", "value"]]


# ----------------------------------------- last-known-value look-back
def get_last_known_values(
    conn,
    segment_ids: list,
    start_ns: int,
    element_ids: list,
) -> dict:
    """For each element, find its most recent value BEFORE start_ns.

    Searches through the provided segments (should include segments that
    end before or overlap start_ns).

    Returns {element_id: last_value_as_string}
    """
    last_values: dict = {}

    # Sort segments by start_time descending so the most recent data is checked first.
    sorted_ids = list(reversed(segment_ids))

    for eid in element_ids:
        if eid in last_values:
            continue
        for sid in sorted_ids:
            table = _event_table_name(sid)
            q = sql.SQL(
                "SELECT COALESCE(value_number::text, value_string) AS value "
                "FROM {} "
                "WHERE element_id = %s AND ts < %s "
                "ORDER BY ts DESC LIMIT 1"
            ).format(sql.Identifier(table))
            try:
                with conn.cursor() as cur:
                    cur.execute(q, (eid, start_ns))
                    row = cur.fetchone()
                if row and row[0] is not None:
                    last_values[eid] = row[0]
                    break  # found for this element, move on
            except Exception as e:
                print(f"[data_extract] Look-back skip segment {sid} "
                      f"for element {eid}: {e}")
                conn.rollback()

    print(f"[data_extract] Found last-known values for "
          f"{len(last_values)}/{len(element_ids)} elements")
    return last_values
