"""
Segment discovery — find which _event_ tables overlap a requested time range.
"""

from datetime import datetime

# Segments with these statuses can be read (from WinCC OA schema constant).
READABLE_STATUSES = (0, 1, 2, 5)


def _datetime_to_ns(dt: datetime) -> int:
    """Convert a Python datetime to nanoseconds since Unix epoch."""
    return int(dt.timestamp() * 1_000_000_000)


def get_segments_for_range(conn, start_time: datetime, end_time: datetime) -> list[dict]:
    """Return segments whose time span overlaps [start_time, end_time).

    Each item is a dict with keys:
        segment_id, group_name, start_time, end_time, status
    """
    start_ns = _datetime_to_ns(start_time)
    end_ns = _datetime_to_ns(end_time)

    sql = """
        SELECT segment_id, group_name, start_time, end_time, status
        FROM segments
        WHERE start_time < %s
          AND end_time   > %s
          AND status IN %s
        ORDER BY start_time;
    """

    with conn.cursor() as cur:
        cur.execute(sql, (end_ns, start_ns, READABLE_STATUSES))
        rows = cur.fetchall()

    segments = [
        {
            "segment_id": r[0],
            "group_name": r[1],
            "start_time": r[2],
            "end_time": r[3],
            "status": r[4],
        }
        for r in rows
    ]

    print(f"[segment_lookup] Found {len(segments)} readable segment(s) "
          f"for range {start_time} -> {end_time}")
    return segments
