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
    validate_active_authorization,
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


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def synthetic_readiness(
    root: Path,
    *,
    code_bindings: dict[str, tuple[str, Path]] | None = None,
    contract_bindings: dict[str, tuple[str, Path]] | None = None,
) -> dict[str, object]:
    """Build the minimum frozen readiness tree needed by the production gate."""
    run_id = root.name
    live = root.parent / "live"
    live.mkdir(parents=True, exist_ok=True)
    if code_bindings is None:
        code_bindings = {}
        for summary_key, manifest_name in (
            ("stage_c_processing_helper_sha256", "stage_c_processing_helper"),
            ("stage_c_processor_sha256", "stage_c_processor"),
            ("stage_c_authorizer_sha256", "stage_c_authorizer"),
            ("stage_c_verifier_sha256", "stage_c_verifier"),
        ):
            path = live / f"{manifest_name}.py"
            path.write_text(f"# {manifest_name}\n", encoding="utf-8")
            code_bindings[summary_key] = (manifest_name, path)

    if contract_bindings is None:
        contract_bindings = {}
        for receipt_key, filename in (
            ("output_schema_sha256", "stage-c01-output-schema.yaml"),
            ("qc_contract_sha256", "stage-c01-source-internal-qc.yaml"),
            ("verification_contract_sha256", "stage-c01-verification-contract.yaml"),
        ):
            path = live / filename
            path.write_text(f"name: {filename}\n", encoding="utf-8")
            contract_bindings[receipt_key] = (filename, path)

    root.mkdir(parents=True)
    template_path = root / "stage_c_authorization.template.json"
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    template["fixed_output_root"] = str((root.parent / "stage_c").resolve())
    write_json(template_path, template)

    source_code = {
        manifest_name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
        for manifest_name, path in code_bindings.values()
    }
    contracts: dict[str, dict[str, object]] = {}
    outputs: dict[str, dict[str, object]] = {
        "stage_c_authorization.template.json": {
            "path": str(template_path.resolve()),
            "bytes": template_path.stat().st_size,
            "sha256": sha256_file(template_path),
        }
    }
    contracts_dir = root / "contracts"
    contracts_dir.mkdir()
    for filename, source in contract_bindings.values():
        frozen = contracts_dir / filename
        frozen.write_bytes(source.read_bytes())
        digest = sha256_file(source)
        contracts[filename] = {
            "source_path": str(source.resolve()),
            "bytes": frozen.stat().st_size,
            "sha256": digest,
        }
        outputs[f"contracts/{filename}"] = {
            "path": str(frozen.resolve()),
            "bytes": frozen.stat().st_size,
            "sha256": digest,
        }

    summary: dict[str, object] = {
        "run_id": run_id,
        "status": "ready_for_separate_stage_c_authorization",
        "stage_c_authorized": False,
        "confirmation_role_eligible": False,
        "sealed_object_body_read_count": 0,
        "archive_decompression_count": 0,
        "candidate_sounding_row_count": 0,
        "candidate_cell_row_count": 0,
        "authorization_template_path": str(template_path.resolve()),
        "authorization_template_sha256": sha256_file(template_path),
        "receipt_report_template_path": str(template_path.resolve()),
        "receipt_report_template_sha256": sha256_file(template_path),
        "verifier_template_path": str(template_path.resolve()),
        "verifier_template_sha256": sha256_file(template_path),
    }
    for summary_key, (_manifest_name, path) in code_bindings.items():
        summary[summary_key] = sha256_file(path)
    for receipt_key, (_filename, path) in contract_bindings.items():
        summary[receipt_key] = sha256_file(path)
    write_json(root / "readiness_lock.json", summary)

    manifest = {
        "run_id": run_id,
        "source_code": source_code,
        "contracts": contracts,
        "outputs": outputs,
        "summary": summary,
    }
    write_json(root / "audit_manifest.json", manifest)
    verification = {
        "run_id": run_id,
        "run_dir": str(root.resolve()),
        "status": "pass",
        "stage_c_authorized": False,
        "confirmation_role_eligible": False,
        "sealed_object_body_read_count": 0,
        "archive_decompression_count": 0,
        "candidate_sounding_row_count": 0,
        "candidate_cell_row_count": 0,
        "audit_manifest_sha256": sha256_file(root / "audit_manifest.json"),
        **{
            key: summary[key]
            for key in (
                "authorization_template_sha256",
                "receipt_report_template_sha256",
                "verifier_template_sha256",
                *code_bindings.keys(),
                *contract_bindings.keys(),
            )
        },
    }
    write_json(root / "verification.json", verification)
    write_json(
        root / "environment_lock.json",
        {
            "environment_digest": "8" * 64,
            "material": {
                "binaries": {
                    name: {"sha256": character * 64, "version_or_help_sha256": character.upper() * 64}
                    for name, character in (("mblist", "9"), ("mbinfo", "a"), ("gzip", "b"))
                }
            },
        },
    )
    write_json(
        root / "fixture_verification.json",
        {"fixture": {"sha256": "3" * 64}, "oracle": {"sha256": "4" * 64}},
    )
    write_json(root / "time_contract_fixture_verification.json", {"status": "pass"})
    return {
        "run_id": run_id,
        "root": root,
        "template_path": template_path,
        "code_bindings": code_bindings,
        "contract_bindings": contract_bindings,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_active_receipt(template_path: Path = TEMPLATE_PATH) -> dict:
    """Build an active receipt that passes the schema gate.

    Starts from the real template (so the template SHA is genuine), drops the
    scaffold-only key authorize removes, and fills every authorize-added key
    with a non-placeholder value. No value contains ``<REQUIRED``.
    """
    template = json.loads(template_path.read_text(encoding="utf-8"))
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
            "authorization_template_sha256": sha256_file(template_path),
            "authorization_script_sha256": "a" * 64,
            "authorization_receipt_sha256": "b" * 64,
            "processor_sha256": "c" * 64,
            "processing_helper_sha256": "d" * 64,
            "verifier_sha256": "e" * 64,
            "permitted_body_read_counts": {".mb58.gz": 192, ".fnv": 0, ".inf": 0, ".fbt": 0},
            "prohibited_external_inputs": ["GEBCO"],
            "source_internal_only": True,
            "stage_c_readiness_run_id": "readiness-run",
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


def bound_active_receipt(bundle: dict[str, object]) -> tuple[dict[str, object], dict]:
    from ncei.code.scs_v2_stage_c_processing import (
        canonical_authorization_receipt_sha256,
        validate_readiness_bundle,
    )

    readiness = validate_readiness_bundle(
        bundle["root"],
        bundle["run_id"],
        code_bindings=bundle["code_bindings"],
        contract_bindings=bundle["contract_bindings"],
    )
    receipt = _valid_active_receipt(bundle["template_path"])
    receipt.update(
        {
            "stage_c_readiness_run_id": readiness["run_id"],
            "stage_c1a_readiness_manifest_sha256": readiness["manifest_sha256"],
            "stage_c1a_readiness_verification_sha256": readiness["verification_sha256"],
            "authorization_script_sha256": readiness["code_hashes"]["stage_c_authorizer_sha256"],
            "processor_sha256": readiness["code_hashes"]["stage_c_processor_sha256"],
            "processing_helper_sha256": readiness["code_hashes"]["stage_c_processing_helper_sha256"],
            "verifier_sha256": readiness["code_hashes"]["stage_c_verifier_sha256"],
            **readiness["contract_hashes"],
        }
    )
    receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
    return readiness, receipt


class VerifySCSV2StageCProcessingTest(unittest.TestCase):
    def setUp(self):
        self.receipt = _valid_active_receipt()
        # Sanity: the builder itself must produce a schema-valid receipt.
        verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)

    def test_valid_active_receipt_passes_gate(self):
        # Baseline: a properly filled receipt is accepted.
        verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)

    def test_shared_receipt_gate_accepts_valid_receipt(self):
        from ncei.code.scs_v2_stage_c_processing import validate_authorization_receipt

        validate_authorization_receipt(self.receipt, TEMPLATE_PATH)

    def test_readiness_rejects_wrong_run_id(self):
        from ncei.code.scs_v2_stage_c_processing import validate_readiness_bundle

        with TemporaryDirectory() as directory:
            bundle = synthetic_readiness(Path(directory) / "expected-run")
            with self.assertRaisesRegex(AssertionError, "run ID"):
                validate_readiness_bundle(
                    bundle["root"],
                    "different-run",
                    code_bindings=bundle["code_bindings"],
                    contract_bindings=bundle["contract_bindings"],
                )

    def test_valid_readiness_bundle_passes_frozen_bindings(self):
        from ncei.code.scs_v2_stage_c_processing import validate_readiness_bundle

        with TemporaryDirectory() as directory:
            bundle = synthetic_readiness(Path(directory) / "readiness-run")
            result = validate_readiness_bundle(
                bundle["root"],
                bundle["run_id"],
                code_bindings=bundle["code_bindings"],
                contract_bindings=bundle["contract_bindings"],
            )
            self.assertEqual(result["run_id"], "readiness-run")
            self.assertEqual(result["template_path"], bundle["template_path"].resolve())

    def test_readiness_rejects_missing_verification(self):
        from ncei.code.scs_v2_stage_c_processing import validate_readiness_bundle

        with TemporaryDirectory() as directory:
            bundle = synthetic_readiness(Path(directory) / "readiness-run")
            (bundle["root"] / "verification.json").unlink()
            with self.assertRaisesRegex(AssertionError, "verification.json"):
                validate_readiness_bundle(
                    bundle["root"],
                    bundle["run_id"],
                    code_bindings=bundle["code_bindings"],
                    contract_bindings=bundle["contract_bindings"],
                )

    def test_readiness_rejects_each_frozen_file_drift(self):
        from ncei.code.scs_v2_stage_c_processing import validate_readiness_bundle

        target_keys = (
            "template",
            "stage_c_processing_helper_sha256",
            "stage_c_processor_sha256",
            "stage_c_authorizer_sha256",
            "stage_c_verifier_sha256",
            "output_schema_sha256",
            "qc_contract_sha256",
            "verification_contract_sha256",
        )
        for target_key in target_keys:
            with self.subTest(target_key=target_key), TemporaryDirectory() as directory:
                bundle = synthetic_readiness(Path(directory) / "readiness-run")
                if target_key == "template":
                    target = bundle["template_path"]
                elif target_key in bundle["code_bindings"]:
                    target = bundle["code_bindings"][target_key][1]
                else:
                    target = bundle["contract_bindings"][target_key][1]
                target.write_text(target.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
                with self.assertRaisesRegex(AssertionError, "mismatch"):
                    validate_readiness_bundle(
                        bundle["root"],
                        bundle["run_id"],
                        code_bindings=bundle["code_bindings"],
                        contract_bindings=bundle["contract_bindings"],
                    )

    def test_receipt_binding_rejects_wrong_readiness_id(self):
        from ncei.code.scs_v2_stage_c_processing import (
            canonical_authorization_receipt_sha256,
            validate_receipt_readiness_bindings,
        )

        with TemporaryDirectory() as directory:
            bundle = synthetic_readiness(Path(directory) / "readiness-run")
            readiness, receipt = bound_active_receipt(bundle)
            validate_receipt_readiness_bindings(receipt, readiness)
            receipt["stage_c_readiness_run_id"] = "wrong-run"
            receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
            with self.assertRaisesRegex(AssertionError, "run ID"):
                validate_receipt_readiness_bindings(receipt, readiness)

    def test_receipt_rejects_each_frozen_sha_drift(self):
        from ncei.code.scs_v2_stage_c_processing import (
            canonical_authorization_receipt_sha256,
            validate_receipt_readiness_bindings,
        )

        fields = (
            "authorization_template_sha256",
            "processing_helper_sha256",
            "processor_sha256",
            "authorization_script_sha256",
            "verifier_sha256",
            "output_schema_sha256",
            "qc_contract_sha256",
            "verification_contract_sha256",
            "stage_c1a_readiness_manifest_sha256",
            "stage_c1a_readiness_verification_sha256",
        )
        for field in fields:
            with self.subTest(field=field), TemporaryDirectory() as directory:
                bundle = synthetic_readiness(Path(directory) / "readiness-run")
                readiness, receipt = bound_active_receipt(bundle)
                receipt[field] = "0" * 64
                receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
                with self.assertRaisesRegex(AssertionError, "mismatch"):
                    validate_receipt_readiness_bindings(receipt, readiness)

    def test_receipt_rejects_prohibited_authorization_flag(self):
        from ncei.code.scs_v2_stage_c_processing import (
            canonical_authorization_receipt_sha256,
            validate_receipt_readiness_bindings,
        )

        with TemporaryDirectory() as directory:
            bundle = synthetic_readiness(Path(directory) / "readiness-run")
            readiness, receipt = bound_active_receipt(bundle)
            receipt["stage_d_confirmation_evaluation_authorized"] = True
            receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
            with self.assertRaisesRegex(AssertionError, "prohibited"):
                validate_receipt_readiness_bindings(receipt, readiness)

    def test_real_authorizer_generates_synthetic_active_receipt(self):
        from ncei.code.authorize_scs_v2_stage_c import PLANNING_LOCK_PATH, materialize_authorization
        from ncei.code.scs_v2_stage_c_processing import (
            validate_readiness_bundle,
            validate_receipt_readiness_bindings,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = synthetic_readiness(root / "readiness-run")
            paths = bundle["code_bindings"]
            contracts = bundle["contract_bindings"]
            output = root / "active-receipt.json"
            receipt = materialize_authorization(
                template_path=bundle["template_path"],
                processing_run_id="synthetic-stage-c",
                authorized_by="synthetic-test",
                authorized_utc="2026-08-09T00:00:00Z",
                output_path=output,
                processor_path=paths["stage_c_processor_sha256"][1],
                verifier_path=paths["stage_c_verifier_sha256"][1],
                processing_helper_path=paths["stage_c_processing_helper_sha256"][1],
                authorization_script_path=paths["stage_c_authorizer_sha256"][1],
                output_schema_path=contracts["output_schema_sha256"][1],
                qc_contract_path=contracts["qc_contract_sha256"][1],
                verification_contract_path=contracts["verification_contract_sha256"][1],
                readiness_root=bundle["root"],
                expected_readiness_run_id=bundle["run_id"],
                stage_c_root=root / "stage_c",
                planning_lock_path=PLANNING_LOCK_PATH,
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), receipt)
            readiness = validate_readiness_bundle(
                bundle["root"],
                bundle["run_id"],
                code_bindings=bundle["code_bindings"],
                contract_bindings=bundle["contract_bindings"],
            )
            validate_receipt_readiness_bindings(receipt, readiness)

    def test_expected_keys_match_added_plus_template_minus_scaffold(self):
        template_keys = set(json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")))
        self.assertEqual(expected_authorization_keys(TEMPLATE_PATH), (template_keys - AUTHORIZE_SCAFFOLD_REMOVED) | AUTHORIZE_ADDED_KEYS)

    def test_gate_rejects_top_level_placeholder(self):
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["parser_environment_digest"] = "<REQUIRED_SHA256_DIGEST>"
        # Recompute the canonical hash so the canonical-hash check passes and the
        # placeholder check is the one that fires.
        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)
        self.assertIn("placeholder", str(ctx.exception).lower())

    def test_gate_rejects_nested_placeholder_recursively(self):
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        # A placeholder nested inside a dict value must be caught (top-level-only
        # scan would miss it).
        self.receipt["permitted_body_read_counts"] = {".mb58.gz": "<REQUIRED_COUNT>", ".fnv": 0, ".inf": 0, ".fbt": 0}
        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)
        self.assertIn("permitted_body_read_counts", str(ctx.exception))

    def test_gate_rejects_wrong_template_sha(self):
        self.receipt["authorization_template_sha256"] = "0" * 64
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)
        self.assertIn("template", str(ctx.exception).lower())

    def test_gate_rejects_missing_field(self):
        del self.receipt["processor_sha256"]
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)
        self.assertIn("missing", str(ctx.exception).lower())

    def test_gate_rejects_extra_field(self):
        self.receipt["unexpected_extra_key"] = "stray"
        from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256

        self.receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(self.receipt)
        with self.assertRaises(AssertionError) as ctx:
            verify_authorization_receipt_schema(self.receipt, TEMPLATE_PATH)
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

    def test_production_chain_uses_shared_readiness_snapshot(self):
        import ncei.code.authorize_scs_v2_stage_c as authorizer_module
        import ncei.code.verify_scs_v2_stage_c_processing as verifier_module
        from ncei.code.prepare_scs_v2_stage_c1a_readiness import AUTHORIZATION_TEMPLATE_SOURCE_PATH
        from ncei.code.scs_v2_stage_c_processing import (
            STAGE_C2_2_READINESS_ROOT,
            STAGE_C2_2_READINESS_RUN_ID,
            STAGE_C2_2_TEMPLATE_PATH,
        )

        self.assertEqual(AUTHORIZATION_TEMPLATE_SOURCE_PATH.resolve(), TEMPLATE_PATH.resolve())
        self.assertEqual(authorizer_module.READINESS_ROOT.resolve(), STAGE_C2_2_READINESS_ROOT.resolve())
        self.assertEqual(verifier_module.READINESS_ROOT.resolve(), STAGE_C2_2_READINESS_ROOT.resolve())
        self.assertEqual(verifier_module.TEMPLATE_PATH.resolve(), STAGE_C2_2_TEMPLATE_PATH.resolve())
        if STAGE_C2_2_TEMPLATE_PATH.is_file():
            verification_path = STAGE_C2_2_READINESS_ROOT / "verification.json"
            self.assertTrue(verification_path.is_file())
            manifest = json.loads((STAGE_C2_2_READINESS_ROOT / "audit_manifest.json").read_text(encoding="utf-8"))
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {STAGE_C2_2_READINESS_ROOT.name, manifest["run_id"], verification["run_id"]},
                {STAGE_C2_2_READINESS_RUN_ID},
            )

    def test_synthetic_producer_output_passes_production_verifier(self):
        """Run the real verifier over producer-built synthetic tables.

        The verifier's default manifest loader remains bound to the sealed
        Stage B manifest. This test injects only a one-object metadata fixture
        and a temporary root, so no sealed body or Stage C output is opened.
        The tables themselves are assembled through the same helper, QC and
        aggregation functions used by the production processor.
        """
        from ncei.code.authorize_scs_v2_stage_c import materialize_authorization
        from ncei.code.scs_v2_stage_c_processing import (
            STAGE_C_PRODUCTION_CODE_BINDINGS,
            STAGE_C_PRODUCTION_CONTRACT_BINDINGS,
        )

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
            "1700000002.000000\t1\t4\t120\t10\t250\t90\n"
        )
        u0_text = (
            "1700000000.000000\t1\t2\t120\t10\t250\t90\n"
            "1700000001.000000\t1\t3\t120\t10\t250\t90\n"
            "1700000002.000000\t1\t4\tnan\t10\t250\t90\n"
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage_root = root / "stage_c"
            run_dir = stage_root / run_id
            bundle = synthetic_readiness(
                root / "readiness-run",
                code_bindings=dict(STAGE_C_PRODUCTION_CODE_BINDINGS),
                contract_bindings=dict(STAGE_C_PRODUCTION_CONTRACT_BINDINGS),
            )
            readiness_root = bundle["root"]
            generated_receipt = root / "generated-authorization-receipt.json"
            materialize_authorization(
                template_path=bundle["template_path"],
                processing_run_id=run_id,
                authorized_by="synthetic-test",
                authorized_utc="2026-08-09T00:00:00Z",
                output_path=generated_receipt,
                processor_path=verifier_module.PROCESSOR_PATH,
                verifier_path=verifier_module.VERIFIER_PATH,
                processing_helper_path=verifier_module.HELPER_PATH,
                authorization_script_path=REPO_ROOT / "ncei/code/authorize_scs_v2_stage_c.py",
                output_schema_path=STAGE_C_PRODUCTION_CONTRACT_BINDINGS["output_schema_sha256"][1],
                qc_contract_path=STAGE_C_PRODUCTION_CONTRACT_BINDINGS["qc_contract_sha256"][1],
                verification_contract_path=STAGE_C_PRODUCTION_CONTRACT_BINDINGS["verification_contract_sha256"][1],
                readiness_root=readiness_root,
                expected_readiness_run_id=bundle["run_id"],
                stage_c_root=stage_root,
            )
            validate_active_authorization(
                generated_receipt,
                run_id,
                readiness_root=readiness_root,
                expected_readiness_run_id=bundle["run_id"],
                stage_c_root=stage_root,
            )
            run_dir.mkdir(parents=True)

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
            soundings = sounding_table.to_pylist()
            self.assertEqual([row["qc_eligible_for_cell"] for row in soundings], [True, False, False])
            for row in soundings[1:]:
                self.assertFalse(row["navigation_valid"])
                self.assertEqual(row["native_quality_state"], "good")
                self.assertEqual(row["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
                self.assertIsNone(row["cell_id"])
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
                parsed_row_count=3,
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
            contributors = pd.read_parquet(run_dir / "cell_cruise_contributors.parquet")
            candidates = pd.read_parquet(run_dir / "cell_cruise_candidates.parquet")
            self.assertEqual(len(contributors), 1)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(int(contributors.iloc[0]["n_soundings_all"]), 1)
            self.assertEqual(int(contributors.iloc[0]["n_qc_eligible"]), 1)
            self.assertEqual(int(candidates.iloc[0]["n_soundings_all"]), 1)
            self.assertEqual(int(candidates.iloc[0]["n_qc_eligible"]), 1)

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

            (run_dir / "authorization_receipt.json").write_bytes(generated_receipt.read_bytes())

            (run_dir / "environment.json").write_text("{}\n", encoding="utf-8")
            (run_dir / "fixture_verification.json").write_text("{}\n", encoding="utf-8")
            (run_dir / "qc_summary.tsv").write_text("metric\tvalue\nsounding_rows\t3\n", encoding="utf-8")
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
                "candidate_sounding_row_count": 3,
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
            self.assertEqual(result["sounding_row_count"], 3)
            self.assertEqual(result["eligible_sounding_row_count"], 1)
            self.assertEqual(result["processing_command_invocation_count"], 4)
            self.assertEqual(result["processing_parser_invocation_count"], 3)
            self.assertEqual(result["independent_verifier_parser_invocation_count"], 0)


if __name__ == "__main__":
    unittest.main()
