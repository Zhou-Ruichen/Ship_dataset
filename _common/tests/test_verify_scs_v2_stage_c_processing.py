"""Production Stage C verifier rejection/closure tests (no sealed body read).

Exercises the verifier's pre-data rejection gate, full synthetic producer path,
and command-count closure without sealed body access. The default ``verify_run``
path remains bound to the real 768-object manifest; the full synthetic test
injects only its metadata manifest and temporary roots.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import ncei.code.verify_scs_v2_stage_c_processing as verifier_module
from ncei.code.process_scs_v2_stage_c_source_internal import (
    aggregate_outputs,
    empty_aggregation_db,
    update_counts_from_batch,
)
from ncei.code.scs_v2_stage_c_processing import (
    ParquetAppender,
    _raw_from_object,
    load_output_schemas,
    ping_review_codes,
    source_field_ledger,
    source_object_id,
    source_processing_row,
    sounding_batch_table,
)
from ncei.code.verify_scs_v2_stage_c_processing import (
    AUTHORIZE_ADDED_KEYS,
    AUTHORIZE_SCAFFOLD_REMOVED,
    close_command_counts,
    expected_authorization_keys,
    verify_authorization_receipt_schema,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c-authorization.template.json"
SCHEMA_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-output-schema.yaml"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_active_receipt() -> dict:
    """Build an active receipt that passes the schema gate.

    Starts from the real template (so the template SHA is genuine), drops the
    scaffold-only key authorize removes, and fills every authorize-added key
    with a non-placeholder value. No value contains ``<REQUIRED``.
    """
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    receipt = {k: v for k, v in template.items() if k not in AUTHORIZE_SCAFFOLD_REMOVED}
    # Replace any template placeholder string with a concrete non-placeholder.
    for key, value in list(receipt.items()):
        if isinstance(value, str) and "<REQUIRED" in value:
            receipt[key] = "concrete-value"
    receipt.update(
        {
            "schema_version": 4,
            "stage_c_authorized": True,
            "authorized_by": "tester",
            "authorized_utc": "2026-08-09T00:00:00Z",
            "authorization_template_sha256": sha256_file(TEMPLATE_PATH),
            "authorization_script_sha256": "a" * 64,
            "authorization_receipt_sha256": "b" * 64,
            "processor_sha256": "c" * 64,
            "processing_helper_sha256": "d" * 64,
            "verifier_sha256": "e" * 64,
            "permitted_body_read_counts": {".mb58.gz": 192, ".fnv": 0, ".inf": 0, ".fbt": 0},
            "prohibited_external_inputs": ["GEBCO"],
            "source_internal_only": True,
            "stage_c1a_readiness_manifest_sha256": "f" * 64,
            "stage_c1a_readiness_verification_sha256": "1" * 64,
            "time_fixture_verification_sha256": "2" * 64,
            "format58_fixture_bytes_sha256": "3" * 64,
            "format58_fixture_oracle_sha256": "4" * 64,
            "fixture_verification_sha256": "5" * 64,
            "stage_c0_planning_lock_sha256": "6" * 64,
            "stage_c0_planning_commit": "7" * 40,
            "parser_environment_digest": "8" * 64,
            "parser_binary_sha256": {"mblist": "9" * 64, "mbinfo": "a" * 64, "gzip": "b" * 64},
            "parser_help_snapshot_sha256": {"mblist": "c" * 64, "mbinfo": "d" * 64, "gzip": "e" * 64},
            "gebco_or_product_comparison_authorized": False,
            "model_comparison_authorized": False,
            "mrar_merge_authorized": False,
            "cross_cruise_aggregation_authorized": False,
            "datum_or_bias_fit_authorized": False,
            "confirmation_role_promotion_authorized": False,
            "confirmation_role_eligible": False,
            "model_or_product_evaluation_authorized": False,
            "stage_d_confirmation_evaluation_authorized": False,
        }
    )
    # Recompute the canonical hash so the canonical-hash check passes too.
    from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

    receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
    return receipt


class VerifySCSV2StageCProcessingTest(unittest.TestCase):
    def setUp(self):
        self.receipt = _valid_active_receipt()
        # Sanity: the builder itself must produce a schema-valid receipt.
        verify_authorization_receipt_schema(self.receipt)

    def test_valid_active_receipt_passes_gate(self):
        # Baseline: a properly filled receipt is accepted.
        verify_authorization_receipt_schema(self.receipt)

    def test_expected_keys_match_added_plus_template_minus_scaffold(self):
        template_keys = set(json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")))
        self.assertEqual(expected_authorization_keys(), (template_keys - AUTHORIZE_SCAFFOLD_REMOVED) | AUTHORIZE_ADDED_KEYS)

    def test_gate_rejects_top_level_placeholder(self):
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["parser_environment_digest"] = "<REQUIRED_SHA256_DIGEST>"
        # Recompute the canonical hash so the canonical-hash check passes and the
        # placeholder check is the one that fires.
        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt)
        self.assertIn("placeholder", str(ctx.exception).lower())

    def test_gate_rejects_nested_placeholder_recursively(self):
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        # A placeholder nested inside a dict value must be caught (top-level-only
        # scan would miss it).
        self.receipt["permitted_body_read_counts"] = {".mb58.gz": "<REQUIRED_COUNT>", ".fnv": 0, ".inf": 0, ".fbt": 0}
        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt)
        self.assertIn("permitted_body_read_counts", str(ctx.exception))

    def test_gate_rejects_wrong_template_sha(self):
        self.receipt["authorization_template_sha256"] = "0" * 64
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt)
        self.assertIn("template", str(ctx.exception).lower())

    def test_gate_rejects_missing_field(self):
        del self.receipt["processor_sha256"]
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt)
        self.assertIn("missing", str(ctx.exception).lower())

    def test_gate_rejects_extra_field(self):
        self.receipt["unexpected_extra_key"] = "stray"
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt)
        self.assertIn("unexpected", str(ctx.exception).lower())

    def test_command_count_closure_768_576_0(self):
        # 192 mb58 objects -> 192 each role, 768 commands, 576 parser commands.
        lines = []
        for i in range(192):
            for role in ("decompression", "mbinfo", "mblist_u3", "mblist_u0"):
                lines.append({"object_id": f"obj{i}", "role": role})
        closure = close_command_counts(lines, expected_per_role=192)
        self.assertEqual(closure["processing_command_invocation_count"], 768)
        self.assertEqual(closure["processing_parser_invocation_count"], 576)
        self.assertEqual(closure["independent_verifier_parser_invocation_count"], 0)
        self.assertEqual(
            closure["command_role_counts"],
            {"decompression": 192, "mbinfo": 192, "mblist_u3": 192, "mblist_u0": 192},
        )

    def test_command_count_closure_rejects_wrong_role_count(self):
        lines = []
        for i in range(191):  # one short
            for role in ("decompression", "mbinfo", "mblist_u3", "mblist_u0"):
                lines.append({"object_id": f"obj{i}", "role": role})
        with self.assertRaises(AssertionError):
            close_command_counts(lines, expected_per_role=192)

    def test_command_count_closure_rejects_unknown_role(self):
        lines = [{"object_id": "obj0", "role": "decompression"} for _ in range(192)]
        with self.assertRaises(AssertionError) as ctx:
            close_command_counts(lines, expected_per_role=192)
        self.assertIn("role set", str(ctx.exception).lower())

    def test_production_chain_consumes_single_template(self):
        # Requirement 6 (approach B): the production authorizer and the production
        # verifier both consume ONE authorization template -- the research v1
        # file -- and the active receipt's authorization_template_sha256 must be
        # the SHA of that exact file. The verifier binds the template via its
        # module-level TEMPLATE_PATH constant; the authorizer binds it via the
        # --template CLI arg. Assert they resolve to the same file and that the
        # receipt SHA the gate enforces is that file's on-disk SHA.
        import ncei.code.verify_scs_v2_stage_c_processing as verifier_module

        # (1) The verifier's template constant resolves to the research template.
        self.assertEqual(verifier_module.TEMPLATE_PATH.resolve(), TEMPLATE_PATH.resolve())
        # (2) The active receipt (built like authorize fills it) binds the same SHA.
        self.assertEqual(self.receipt["authorization_template_sha256"], sha256_file(TEMPLATE_PATH))
        # (3) The readiness producer binds the SAME production template path, so the
        # readiness manifest and the production chain reference one file/SHA.
        from ncei.code.prepare_scs_v2_stage_c1a_readiness import AUTHORIZATION_TEMPLATE_PATH

        self.assertEqual(AUTHORIZATION_TEMPLATE_PATH.resolve(), TEMPLATE_PATH.resolve())
        self.assertTrue(TEMPLATE_PATH.is_file())

    def test_synthetic_producer_output_passes_production_verifier(self):
        """Run the real verifier over producer-built synthetic tables.

        The verifier's default manifest loader remains bound to the sealed
        Stage B manifest. This test injects only a one-object metadata fixture
        and a temporary root, so no sealed body or Stage C output is opened.
        The tables themselves are assembled through the same helper, QC and
        aggregation functions used by the production processor.
        """
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        run_id = "synthetic-production-verifier"
        relative = "objects/TN352/synthetic.mb58.gz"
        source_bytes = b"synthetic-format58-fixture"
        object_record = {
            "relative_path": relative,
            "filename": "synthetic.mb58.gz",
            "source_object_role": "primary_sounding_source",
            "format": ".mb58.gz",
            "bytes": len(source_bytes),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "official_cruise_id": "TN352",
        }
        u3_text = (
            "1700000000.000000\t1\t2\t120\t10\t250\t90\n"
            "1700000001.000000\t1\t3\tnan\t10\t250\t90\n"
        )
        u0_text = (
            "1700000000.000000\t1\t2\t120\t10\t250\t90\n"
            "1700000001.000000\t1\t3\t120\t10\t250\t90\n"
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage_root = root / "stage_c"
            run_dir = stage_root / run_id
            run_dir.mkdir(parents=True)
            readiness_root = root / "readiness"
            readiness_root.mkdir()
            (readiness_root / "audit_manifest.json").write_text("{}\n", encoding="utf-8")
            (readiness_root / "verification.json").write_text("{}\n", encoding="utf-8")

            u3_path = root / "u3.tsv"
            u0_path = root / "u0.tsv"
            u3_path.write_text(u3_text, encoding="ascii")
            u0_path.write_text(u0_text, encoding="ascii")
            raw_path = root / "raw.parquet"
            raw_result = _raw_from_object(
                source_object_id("20260805T230449Z", relative),
                u3_path,
                u0_path,
                root / "u0.sqlite",
                raw_path,
            )
            self.assertIsNone(raw_result[2], raw_result)

            schemas = load_output_schemas(SCHEMA_PATH)
            review = ping_review_codes(raw_path)
            raw_batch = next(pq.ParquetFile(raw_path).iter_batches())
            sounding_table = sounding_batch_table(
                raw_batch,
                run_id,
                "20260805T230449Z",
                object_record,
                "e" * 64,
                "c" * 64,
                review,
                schemas["sounding_lineage.parquet"],
            )
            sounding_path = run_dir / "sounding_lineage.parquet"
            pq.write_table(sounding_table, sounding_path)

            object_id = source_object_id("20260805T230449Z", relative)
            processing_row = source_processing_row(
                run_id,
                "20260805T230449Z",
                object_record,
                object_id,
                body_read_authorized=True,
                body_read_performed=True,
                parser_name="MB-System",
                parser_version="5.8.3beta16",
                parser_source_commit="1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422",
                parser_environment_digest="e" * 64,
                command_sha256="c" * 64,
                decompressed_sha256="d" * 64,
                parse_status="pass",
                parsed_row_count=2,
                error_code=None,
                error_detail=None,
            )
            processing_writer = ParquetAppender(run_dir / "source_object_processing.parquet", schemas["source_object_processing.parquet"])
            processing_writer.append([processing_row])
            processing_writer.close()

            ledger_writer = ParquetAppender(run_dir / "field_recovery_ledger.parquet", schemas["field_recovery_ledger.parquet"])
            ledger_writer.append(source_field_ledger("TN352", object_id, relative, object_record["sha256"], "c" * 64, parsed=True))
            ledger_writer.close()

            database = empty_aggregation_db(run_dir / "aggregation.sqlite")
            database.execute("CREATE TABLE object_map(source_object_id TEXT PRIMARY KEY, source_object_relative_path TEXT, source_object_sha256 TEXT)")
            database.execute("INSERT INTO object_map VALUES (?,?,?)", (object_id, relative, object_record["sha256"]))
            counts: dict[tuple[str, str, str], dict[str, object]] = {}
            data = sounding_table.to_pydict()
            update_counts_from_batch(counts, data)
            eligible_rows = [
                (
                    data["cell_id"][index],
                    data["official_cruise_id"][index],
                    data["source_object_id"][index],
                    int(data["parser_ping_index"][index]),
                    float(data["depth_m_positive_down"][index]),
                    int(pd.Timestamp(data["time_utc"][index]).value // 1_000),
                )
                for index, eligible in enumerate(data["qc_eligible_for_cell"])
                if eligible
            ]
            database.executemany(
                "INSERT INTO eligible(cell_id,cruise_id,source_object_id,parser_ping_index,depth,epoch_us) VALUES (?,?,?,?,?,?)",
                eligible_rows,
            )
            aggregate_outputs(
                run_id,
                schemas,
                database,
                counts,
                run_dir / "cell_cruise_contributors.parquet",
                run_dir / "cell_cruise_candidates.parquet",
            )
            database.commit()
            database.close()

            closure_schema = pa.schema(
                [
                    ("source_object_id", pa.string()),
                    ("official_cruise_id", pa.string()),
                    ("source_object_relative_path", pa.string()),
                    ("source_object_format", pa.string()),
                    ("source_object_role", pa.string()),
                    ("manifest_bytes", pa.int64()),
                    ("manifest_sha256", pa.string()),
                    ("pre_read_bytes", pa.int64()),
                    ("pre_read_sha256", pa.string()),
                    ("post_read_bytes", pa.int64()),
                    ("post_read_sha256", pa.string()),
                    ("body_read_authorized", pa.bool_()),
                    ("body_read_performed", pa.bool_()),
                    ("closure_status", pa.string()),
                    ("error", pa.string()),
                ]
            )
            closure = {
                "source_object_id": object_id,
                "official_cruise_id": "TN352",
                "source_object_relative_path": relative,
                "source_object_format": ".mb58.gz",
                "source_object_role": "primary_sounding_source",
                "manifest_bytes": len(source_bytes),
                "manifest_sha256": object_record["sha256"],
                "pre_read_bytes": len(source_bytes),
                "pre_read_sha256": object_record["sha256"],
                "post_read_bytes": len(source_bytes),
                "post_read_sha256": object_record["sha256"],
                "body_read_authorized": True,
                "body_read_performed": True,
                "closure_status": "pass",
                "error": None,
            }
            pq.write_table(pa.Table.from_pylist([closure], schema=closure_schema), run_dir / "object_access_closure.parquet")

            receipt = _valid_active_receipt()
            receipt.update(
                {
                    "processing_run_id": run_id,
                    "fixed_output_root": str(stage_root.resolve()),
                    "processor_sha256": sha256_file(verifier_module.PROCESSOR_PATH),
                    "verifier_sha256": sha256_file(verifier_module.VERIFIER_PATH),
                    "processing_helper_sha256": sha256_file(verifier_module.HELPER_PATH),
                    "stage_c1a_readiness_manifest_sha256": sha256_file(readiness_root / "audit_manifest.json"),
                    "stage_c1a_readiness_verification_sha256": sha256_file(readiness_root / "verification.json"),
                }
            )
            receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
            (run_dir / "authorization_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            (run_dir / "environment.json").write_text("{}\n", encoding="utf-8")
            (run_dir / "fixture_verification.json").write_text("{}\n", encoding="utf-8")
            (run_dir / "qc_summary.tsv").write_text("metric\tvalue\nsounding_rows\t2\n", encoding="utf-8")
            (run_dir / "audit_report.md").write_text("# Synthetic Stage C fixture\n", encoding="utf-8")
            command_lines = [
                {"object_id": object_id, "role": role}
                for role in ("decompression", "mbinfo", "mblist_u3", "mblist_u0")
            ]
            (run_dir / "command_ledger.jsonl").write_text(
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in command_lines),
                encoding="utf-8",
            )
            access = {
                "sealed_object_body_read_count": 1,
                "decompression_count": 1,
                "mb58_body_read_count": 1,
                "fnv_body_read_count": 0,
                "inf_body_read_count": 0,
                "fbt_body_read_count": 0,
                "candidate_sounding_row_count": 2,
                "candidate_cell_cruise_contributor_row_count": len(pd.read_parquet(run_dir / "cell_cruise_contributors.parquet")),
                "candidate_cell_row_count": len(pd.read_parquet(run_dir / "cell_cruise_candidates.parquet")),
                "external_product_or_model_reference_count": 0,
                "mrar_merge_count": 0,
                "cross_cruise_aggregation_count": 0,
                "datum_or_bias_fit_count": 0,
                "confirmation_role_eligible": False,
            }
            (run_dir / "access_lock.json").write_text(json.dumps(access, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            output_names = [
                "authorization_receipt.json",
                "source_object_processing.parquet",
                "sounding_lineage.parquet",
                "cell_cruise_contributors.parquet",
                "cell_cruise_candidates.parquet",
                "field_recovery_ledger.parquet",
                "object_access_closure.parquet",
                "aggregation.sqlite",
                "environment.json",
                "fixture_verification.json",
                "qc_summary.tsv",
                "audit_report.md",
                "command_ledger.jsonl",
                "access_lock.json",
            ]
            output_files = {
                name: {"bytes": (run_dir / name).stat().st_size, "sha256": sha256_file(run_dir / name)}
                for name in output_names
            }
            (run_dir / "audit_manifest.json").write_text(
                json.dumps(
                    {
                        "status": "processed_pending_independent_verification",
                        "processing_run_id": run_id,
                        "sealed_archive_manifest_sha256": verifier_module.MANIFEST_SHA256,
                        "stage_b_verification_sha256": verifier_module.STAGE_B_VERIFICATION_SHA256,
                        "output_files": output_files,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            manifest = pd.DataFrame([object_record])
            result = verifier_module.verify_run(
                run_dir,
                stage_c_root=stage_root,
                readiness_root=readiness_root,
                manifest_bundle=(manifest, {}, {}),
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["sounding_row_count"], 2)
            self.assertEqual(result["eligible_sounding_row_count"], 1)
            self.assertEqual(result["processing_command_invocation_count"], 4)
            self.assertEqual(result["processing_parser_invocation_count"], 3)
            self.assertEqual(result["independent_verifier_parser_invocation_count"], 0)


if __name__ == "__main__":
    unittest.main()
