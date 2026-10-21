"""Remote platforms-tree enumeration and URL-plan path mapping."""

import concurrent.futures as cf
import html
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit

import pandas as pd

from . import CHANNEL_DIRS, SHIPS

ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
LINK_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
SIZE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value))
    temp.replace(path)


def parse_size(text: str) -> int | None:
    match = re.fullmatch(r"([\d.]+)\s*([KMGT]?)", text.strip().replace(",", ""))
    return int(float(match[1]) * SIZE_UNITS[match[2]]) if match else None


def safe_relative(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError(f"invalid relative path: {value!r}")
    if any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError(f"invalid relative path: {value!r}")
    return value


def parse_listing(text: str, url: str):
    """Parse Apache data rows, excluding navigation and parent links."""
    if not re.search(r"<(?:title|h1)\b[^>]*>\s*Index of\b", text, re.I):
        raise ValueError(f"not an Apache directory listing: {url}")
    dirs, files = [], {}
    for row in ROW_RE.findall(text):
        link = LINK_RE.search(row)
        if not link:
            continue
        href = html.unescape(link[1])
        if href.startswith(("?", "#")) or href in ("../", "./"):
            continue
        child = urljoin(url, href)
        if not child.startswith(url) or child == url:
            continue
        if urlsplit(child).query or urlsplit(child).fragment:
            continue
        name = unquote(urlsplit(child).path.rstrip("/").rsplit("/", 1)[-1])
        safe_relative(name)
        if href.endswith("/"):
            dirs.append(child)
        else:
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.I | re.S)
            if len(cells) < 3:
                raise ValueError(f"incomplete listing row: {url}")
            size = html.unescape(re.sub("<[^>]+>", "", cells[-1])).strip()
            files[name] = (child, parse_size(size))
    return dirs, files


def cache_name(work: Path, url: str) -> Path:
    rel = url.split("/ships/", 1)[-1].rstrip("/") or "ships_index"
    return work / "lists" / (rel.replace("/", "__") + ".html")


def platform_parts(url: str) -> tuple[str, str, str]:
    path = urlsplit(url).path
    marker = "/platforms/ocean/ships/"
    if marker not in path or path.endswith("/"):
        raise ValueError(f"not a platforms-tree file URL: {url}")
    ship, survey, tail = path.split(marker, 1)[1].split("/", 2)
    if "/MB/" in "/" + tail:
        tail = ("/" + tail).split("/MB/", 1)[1]
    elif tail.startswith("multibeam/"):
        tail = tail[len("multibeam/"):]
    return tuple(safe_relative(unquote(x)) for x in (ship, survey, tail))


def target_path(raw: Path, item: dict) -> Path:
    """Read both platforms layouts; write new cruises in the 41 layout."""
    channel = item.get("channel", "platforms_tree")
    base = raw / CHANNEL_DIRS[channel]
    survey = safe_relative(item["survey_id"])
    if channel == "platforms_tree":
        ship, url_survey, rel = platform_parts(item["url"])
        if survey != url_survey:
            raise ValueError(f"survey_id disagrees with URL: {survey} / {url_survey}")
        rel = safe_relative(item.get("rel", rel))
        direct, nested = base / survey / rel, base / ship / survey / rel
        for path in (direct, nested):
            if path.exists() or Path(str(path) + ".part").exists():
                return path
        if (base / ship / survey).is_dir() and not (base / survey).is_dir():
            return nested
        return direct
    if channel == "r2r":
        return base / safe_relative(item.get("rel", f"{survey}.tar.gz"))
    name = unquote(PurePosixPath(urlsplit(item["url"]).path).name)
    return base / survey / safe_relative(item.get("rel", name))


def load_plan(path: Path, channel: str) -> list[dict]:
    """Read successful log URLs or an explicit JSON/JSONL/TSV URL plan."""
    if path.suffix == ".parquet":
        rows = pd.read_parquet(path).to_dict("records")
    elif path.suffix == ".json":
        rows = json.loads(path.read_text())
    elif path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    else:
        rows = pd.read_csv(path, sep="\t", keep_default_na=False).to_dict("records")
    result = {}
    for row in rows:
        if row.get("channel", channel) != channel:
            continue
        if row.get("status", "ok") != "ok":
            continue
        url = row.get("url") or row.get("source_url")
        if not url or urlsplit(url).scheme not in ("http", "https") or urlsplit(url).path.endswith("/"):
            raise ValueError(f"not a file URL: {url}")
        item = {"survey_id": str(row["survey_id"]), "channel": channel, "url": url}
        for key in ("rel", "sha256"):
            if pd.notna(row.get(key)) and row.get(key):
                item[key] = str(row[key])
        if "bytes" in row and pd.notna(row["bytes"]) and row["bytes"] != "":
            item["exact_bytes"] = int(row["bytes"])
        elif row.get("exact_bytes") is not None:
            item["exact_bytes"] = int(row["exact_bytes"])
        expected = row.get("expected", item.get("exact_bytes"))
        item["expected"] = int(expected) if pd.notna(expected) and expected != "" else None
        if channel != "platforms_tree" and not re.fullmatch(r"[0-9a-fA-F]{64}", item.get("sha256", "")):
            raise ValueError(f"{channel} URL plan requires sha256: {url}")
        result[(channel, url)] = item
    if not result:
        raise ValueError(f"no successful {channel} file URLs in {path}")
    return list(result.values())


def listing_failures(trees: dict) -> dict:
    return {sid: (tree.get("error") or "empty inventory") if tree else "unresolved survey"
            for sid, tree in trees.items() if not tree or tree.get("error") or not tree.get("files")}


def inventory(catalog: Path, work: Path, transport, workers=8, refresh=False) -> dict:
    wanted = pd.read_csv(catalog, sep="\t", dtype=str).surveyId.tolist()
    if not wanted:
        raise ValueError("empty survey catalog")
    trees_path = work / "trees.json"
    trees = json.loads(trees_path.read_text()) if trees_path.exists() and not refresh else {}
    pending = [s for s in wanted if s not in trees or s in listing_failures({s: trees[s]})]
    if not pending:
        write_json(work / "inventory_errors.json", {})
        return {s: trees[s] for s in wanted}
    errors = {}

    def list_dir(url):
        text = transport.fetch_text(url, cache_name(work, url), refresh)
        if text is None:
            return None, None
        try:
            return parse_listing(text, url)
        except ValueError:
            cache_name(work, url).unlink(missing_ok=True)
            return None, None

    index = transport.fetch_text(SHIPS, work / "ships_index.html", refresh)
    found = None
    if index is not None:
        try:
            found, _ = parse_listing(index, SHIPS)
        except ValueError:
            (work / "ships_index.html").unlink(missing_ok=True)
    platforms_path = work / "platforms.json"
    platforms = json.loads(platforms_path.read_text()) if platforms_path.exists() and not refresh else {}
    if found is not None:
        todo = [u for u in found if not platforms.get(unquote(u[len(SHIPS):].rstrip("/")))]
        with cf.ThreadPoolExecutor(max_workers=workers) as executor:
            for url, (dirs, _) in zip(todo, executor.map(list_dir, todo)):
                key = unquote(url[len(SHIPS):].rstrip("/"))
                if dirs is None:
                    errors[url] = "failed:listing"
                    platforms.pop(key, None)
                else:
                    platforms[key] = [unquote(urlsplit(d).path.rstrip("/").rsplit("/", 1)[1]) for d in dirs]
        write_json(platforms_path, platforms)
    else:
        errors[SHIPS] = "failed:listing"
    resolved = {}
    for platform, surveys in platforms.items():
        for survey in surveys:
            resolved.setdefault(survey, platform)
    write_json(work / "sid2platform.json", {s: resolved.get(s) for s in wanted})

    def walk(survey):
        platform = resolved.get(survey)
        root = f"{SHIPS}{quote(platform, safe='')}/{quote(survey, safe='')}/multibeam/" if platform else None
        tree = {"root": root, "error": None, "files": {}}
        if root is None:
            tree["error"] = "failed:listing: unresolved platform"
            return survey, tree
        todo, seen = [root], set()
        while todo:
            url = todo.pop()
            if url in seen:
                continue
            seen.add(url)
            dirs, files = list_dir(url)
            if files is None:
                tree["error"] = f"listing failed: {url}"
                return survey, tree
            for child, size in files.values():
                _, _, rel = platform_parts(child)
                tree["files"][rel] = [child, size]
            todo.extend(dirs)
        if not tree["files"]:
            tree["error"] = "failed:listing: empty multibeam tree"
        return survey, tree

    with cf.ThreadPoolExecutor(max_workers=workers) as executor:
        for index, (survey, tree) in enumerate(executor.map(walk, pending), 1):
            trees[survey] = tree
            if index % 20 == 0:
                write_json(trees_path, trees)
    write_json(trees_path, trees)
    selected = {s: trees[s] for s in wanted}
    errors.update(listing_failures(selected))
    write_json(work / "inventory_errors.json", errors)
    return selected


def tree_items(trees: dict) -> list[dict]:
    return [{"survey_id": sid, "rel": rel, "url": url, "expected": size}
            for sid, tree in sorted(trees.items()) if tree
            for rel, (url, size) in tree["files"].items()]
