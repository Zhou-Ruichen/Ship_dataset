"""Downloader checks use temporary files and loopback HTTP, not upstream data."""

import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from ncei.download import SHIPS
from ncei.download.__main__ import main
from ncei.download.download import diff, fetch
from ncei.download.inventory import (
    inventory, listing_failures, load_plan, parse_listing, platform_parts,
    target_path, tree_items, write_json,
)
from ncei.download.transport import DiskFloorError, Transport, header_total
from ncei.download.verify import completeness


def listing(*names):
    rows = "".join(
        f'<tr><td><a href="{name}">{name}</a></td><td>date</td><td>10</td></tr>'
        for name in names)
    return f"<title>Index of /</title><table>{rows}</table>"


class TestNceiDownload(unittest.TestCase):
    def test_parse_listing_and_size(self):
        html = """<title>Index of /x</title><table>
        <tr><td><a href="sub/">sub/</a></td><td>x</td><td>-</td></tr>
        <tr><td><a href="a.gz">a.gz</a></td><td>x</td><td>1.5K</td></tr></table>"""
        dirs, files = parse_listing(html, "https://example.test/x/")
        self.assertEqual(dirs, ["https://example.test/x/sub/"])
        self.assertEqual(files["a.gz"][1], 1536)

    def test_url_to_relative_path_for_both_layouts(self):
        classic = "https://data.ngdc.noaa.gov/platforms/ocean/ships/roger_revelle/HNRO14RR/multibeam/data/version1/MB/a.gz"
        direct = "https://data.ngdc.noaa.gov/platforms/ocean/ships/atlantis/AT42-10/multibeam/level_00/a.gz"
        self.assertEqual(platform_parts(classic), ("roger_revelle", "HNRO14RR", "a.gz"))
        self.assertEqual(platform_parts(direct), ("atlantis", "AT42-10", "level_00/a.gz"))
        with tempfile.TemporaryDirectory() as root:
            raw = Path(root)
            self.assertEqual(target_path(raw, {"survey_id": "HNRO14RR", "channel": "platforms_tree", "url": classic}), raw / "platforms_tree/HNRO14RR/a.gz")
            nested = raw / "platforms_tree/roger_revelle/HNRO14RR"
            nested.mkdir(parents=True)
            self.assertEqual(target_path(raw, {"survey_id": "HNRO14RR", "channel": "platforms_tree", "url": classic}), nested / "a.gz")

    def test_failed_inventory_is_not_complete(self):
        with tempfile.TemporaryDirectory() as root:
            raw = Path(root) / "raw"
            (raw / "platforms_tree/S1").mkdir(parents=True)
            trees = {"S1": {"root": "x", "error": "failed:listing", "files": {}}}
            result = completeness(trees, raw)
            self.assertEqual(result.loc[0, "status"], "listing_failed")

    def test_null_and_empty_trees_are_failures(self):
        self.assertEqual(set(listing_failures({
            "S1": None, "S2": {"error": None, "files": {}},
        })), {"S1", "S2"})

    def test_listing_filters_navigation_and_decodes_names(self):
        dirs, files = parse_listing(listing("../", "?C=N;O=A", "a%20b.gz", "sub/"), SHIPS)
        self.assertEqual(dirs, [SHIPS + "sub/"])
        self.assertEqual(set(files), {"a b.gz"})
        with self.assertRaises(ValueError):
            parse_listing("<html>upstream unavailable</html>", SHIPS)
        with self.assertRaises(ValueError):
            parse_listing(listing("%2e%2e/"), SHIPS)

    def test_failed_platform_probe_is_retried(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            catalog = work / "catalog.tsv"
            catalog.write_text("surveyId\nS1\n")
            # 41 could persist failed platform probes as an empty list.
            write_json(work / "platforms.json", {"ship": []})
            write_json(work / "trees.json", {"S1": None})
            transport = Mock()
            transport.fetch_text.side_effect = [listing("ship/"), None]
            first = inventory(catalog, work, transport, workers=1)
            self.assertIn("S1", listing_failures(first))
            self.assertNotIn("ship", json.loads((work / "platforms.json").read_text()))
            transport.fetch_text.side_effect = [
                listing("ship/"), listing("S1/"), listing("a.gz"),
            ]
            second = inventory(catalog, work, transport, workers=1)
            self.assertFalse(listing_failures(second))
            self.assertEqual(set(second["S1"]["files"]), {"a.gz"})

    def test_child_probe_failure_preserves_partial_inventory(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            catalog = work / "catalog.tsv"
            catalog.write_text("surveyId\nS1\n")
            transport = Mock()
            transport.fetch_text.side_effect = [
                listing("ship/"), listing("S1/"), listing("a.gz", "sub/"), None,
            ]
            trees = inventory(catalog, work, transport, workers=1)
            self.assertEqual(set(trees["S1"]["files"]), {"a.gz"})
            self.assertIn("S1", listing_failures(trees))

    def test_diff_keeps_41_queue_shape(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            url = SHIPS + "ship/S1/multibeam/data/version1/MB/a.gz"
            trees = {"S1": {"root": "x", "error": None, "files": {"a.gz": [url, 10000]}}}
            todo = diff(tree_items(trees), root / "raw", root / "work")
            self.assertEqual(todo, [{
                "survey_id": "S1", "url": url, "rel": "a.gz",
                "expected": 10000, "reason": "absent",
            }])
            path = root / "raw/platforms_tree/S1/a.gz"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"x" * 100)
            self.assertEqual(diff(tree_items(trees), root / "raw", root / "work")[0]["reason"], "short")

    def test_url_plan_channels_keep_existing_paths_and_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            plan = root / "plan.json"
            row = {"survey_id": "S1", "source_url": "https://example.test/fileset/123",
                   "sha256": "a" * 64, "bytes": 20, "status": "ok"}
            plan.write_text(json.dumps([row]))
            item = load_plan(plan, "r2r")[0]
            self.assertEqual(item["exact_bytes"], 20)
            self.assertEqual(target_path(root, item), root / "r2r/S1.tar.gz")
            row["source_url"] = "https://example.test/s1.h77t"
            plan.write_text(json.dumps([row]))
            item = load_plan(plan, "m77t_static")[0]
            self.assertEqual(target_path(root, item), root / "mgd77t_static/S1/s1.h77t")
            row.pop("sha256")
            plan.write_text(json.dumps([row]))
            with self.assertRaises(ValueError):
                load_plan(plan, "m77t_static")

    def test_headers_do_not_reuse_redirect_size(self):
        with tempfile.TemporaryDirectory() as root:
            header = Path(root) / "headers"
            header.write_text("HTTP/1.1 301 Moved\nContent-Length: 50\n\nHTTP/2 200 OK\n\n")
            self.assertIsNone(header_total(header))
            header.write_text("HTTP/1.1 416 Range\nContent-Range: bytes */123\nContent-Length: 20\n\n")
            self.assertEqual(header_total(header), 123)

    def test_failed_listing_is_not_cached_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "listing.html"
            transport = Transport([""])

            def fail(url, dest):
                dest.write_text("partial response")
                return 200, 16, 18

            with patch.object(transport, "curl", side_effect=fail), patch("time.sleep"):
                self.assertIsNone(transport.fetch_text("https://example.test/", cache))
            self.assertFalse(cache.exists())

    def test_short_http_response_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            url = SHIPS + "ship/S1/multibeam/data/version1/MB/a.gz"
            item = {"survey_id": "S1", "url": url, "expected": 1500}
            transport = Mock()
            transport.next_proxy.return_value = ""

            def short(url, dest, **kwargs):
                dest.write_bytes(b"x" * 1000)
                kwargs["headers"].write_text("HTTP/2 200\nContent-Length: 1500\n\n")
                return 200, 1000, 18

            transport.curl.side_effect = short
            result = fetch([item], root / "raw", root / "work", transport, workers=1, attempts=1)
            self.assertEqual(result["failed"], 1)
            self.assertFalse((root / "raw/platforms_tree/S1/a.gz").exists())
            self.assertTrue((root / "raw/platforms_tree/S1/a.gz.part").exists())

    def test_checksum_failure_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            item = {"survey_id": "S1", "channel": "r2r", "url": "https://example.test/1",
                    "expected": 3, "sha256": "a" * 64}
            transport = Mock()
            transport.next_proxy.return_value = ""

            def wrong(url, dest, **kwargs):
                dest.write_bytes(b"bad")
                kwargs["headers"].write_text("HTTP/2 200\nContent-Length: 3\n\n")
                return 200, 3, 0

            transport.curl.side_effect = wrong
            result = fetch([item], root / "raw", root / "work", transport, workers=1, attempts=1)
            self.assertEqual(result["failed"], 1)
            self.assertFalse((root / "raw/r2r/S1.tar.gz").exists())
            record = json.loads(next((root / "work").glob("download-*.jsonl")).read_text())
            self.assertEqual(record["status"], "failed:sha256")

    def test_curl_resumes_a_valid_partial_file(self):
        data = b"round-2 test bytes\n" * 100
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                request_range = self.headers.get("Range")
                requests.append(request_range)
                offset = int(request_range.split("=")[1].split("-")[0])
                self.send_response(206)
                self.send_header("Content-Length", str(len(data) - offset))
                self.send_header("Content-Range", f"bytes {offset}-{len(data)-1}/{len(data)}")
                self.end_headers()
                self.wfile.write(data[offset:])

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as root:
                root = Path(root)
                part = root / "raw/r2r/S1.tar.gz.part"
                part.parent.mkdir(parents=True)
                part.write_bytes(data[:250])
                item = {"survey_id": "S1", "channel": "r2r",
                        "url": f"http://127.0.0.1:{server.server_port}/file",
                        "exact_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                result = fetch([item], root / "raw", root / "work",
                               Transport([""]), workers=1, attempts=1)
                self.assertEqual(result["failed"], 0)
                self.assertEqual(part.with_suffix("").read_bytes(), data)
                self.assertEqual(requests, ["bytes=250-"])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_disk_floor_records_failure_without_promoting(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            transport = Mock()
            transport.next_proxy.return_value = ""
            transport.curl.side_effect = DiskFloorError("full")
            item = {"survey_id": "S1", "channel": "r2r", "url": "https://example.test/1"}
            with self.assertRaises(DiskFloorError):
                fetch([item], root / "raw", root / "work", transport, workers=1)
            record = json.loads(next((root / "work").glob("download-*.jsonl")).read_text())
            self.assertEqual(record["status"], "failed:disk_floor")

    def test_run_does_not_finish_on_zero_files_with_failed_inventory(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            args = ["run", "--work", str(root / "work"), "--raw", str(root / "raw"),
                    "--log", str(root / "log.parquet"), "--disk-floor-gb", "0",
                    "--max-rounds", "1", "--interval", "0"]
            with patch("ncei.download.__main__.inventory", return_value={"S1": None}):
                self.assertEqual(main(args), 1)
            good = {"S1": {"error": None, "files": {
                "a.gz": [SHIPS + "ship/S1/multibeam/a.gz", 3],
            }}}
            path = root / "raw/platforms_tree/S1/a.gz"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"abc")
            with patch("ncei.download.__main__.inventory", return_value=good):
                self.assertEqual(main(args), 0)


if __name__ == "__main__":
    unittest.main()
