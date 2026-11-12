"""Detect temporal overlap between source formats in a cruise."""

from __future__ import annotations

from itertools import combinations


def interval_union(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def interval_intersection(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> list[tuple[int, int]]:
    overlap = []
    i = j = 0
    while i < len(left) and j < len(right):
        start, end = max(left[i][0], right[j][0]), min(left[i][1], right[j][1])
        if start <= end:
            overlap.append((start, end))
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return interval_union(overlap)


def format_time_summary(rows: list[dict]) -> dict:
    formats = sorted({row["mb_format"] for row in rows if row["status"] == "ok"})
    counts, intervals = [], {}
    for fmt in formats:
        group = [row for row in rows if row["status"] == "ok" and row["mb_format"] == fmt]
        union = interval_union([(row["ping_time_start_us"], row["ping_time_end_us"]) for row in group
                                if row["ping_time_start_us"] is not None])
        intervals[fmt] = union
        counts.append({"mb_format": fmt, "n_files": len(group), "n_beams": sum(row["n_rows"] for row in group),
                       "intervals_us": [list(interval) for interval in union]})
    overlaps = []
    for left, right in combinations(formats, 2):
        union = interval_intersection(intervals[left], intervals[right])
        if union:
            overlaps.append({"left_format": left, "right_format": right, "intervals_us": [list(x) for x in union],
                             "overlap_us": sum(end - start for start, end in union)})
    return {"formats": formats, "format_counts": counts, "format_overlaps": overlaps,
            "format_overlap_us": sum(row["overlap_us"] for row in overlaps)}
