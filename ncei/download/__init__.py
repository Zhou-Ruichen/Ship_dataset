"""Resumable NCEI round-2 acquisition."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = REPO_ROOT / "ncei/raw_round2"
DEFAULT_LOG = REPO_ROOT / "ncei/manifests/round2_download_log.parquet"
DEFAULT_CATALOG = REPO_ROOT / "ncei/derived/mbbdb_value_ranking/order_tier_A.tsv"
DEFAULT_WORK = Path("/tmp/tierA_gapfill")
DEFAULT_PROXIES = ["http://127.0.0.1:2085"]
SHIPS = "https://data.ngdc.noaa.gov/platforms/ocean/ships/"
CHANNEL_DIRS = {
    "platforms_tree": "platforms_tree", "r2r": "r2r", "m77t_static": "mgd77t_static",
}
LOG_COLUMNS = [
    "survey_id", "channel", "source_url", "bytes", "sha256",
    "downloaded_at_utc", "status", "worker", "port",
]
GIB = 1024 ** 3
