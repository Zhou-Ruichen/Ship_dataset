"""Compatible JSONL merging with a backup and atomic parquet replacement."""

import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import LOG_COLUMNS


def merge(work: Path, path: Path) -> int:
    parts = [p for p in sorted(work.glob("download-*.jsonl")) if p.stat().st_size]
    if not parts:
        print("merge: no records")
        return 0
    new = pd.concat([pd.read_json(p, lines=True) for p in parts], ignore_index=True)
    # Keep 41's historical metadata rows; completion never depends on them.
    new = new[new.status.astype(str).str.startswith(("ok", "tierA"))]
    if new.empty:
        print("merge: no successful records")
        return 0
    data = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=LOG_COLUMNS)
    combined = pd.concat([data[LOG_COLUMNS], new[LOG_COLUMNS]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["channel", "source_url"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(f".parquet.bak-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}")
        shutil.copy2(path, backup)
        print(f"merge backup: {backup}", flush=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    combined.to_parquet(temp, index=False)
    temp.replace(path)
    print(f"merge: {len(data)} -> {len(combined)} rows", flush=True)
    return len(combined)
