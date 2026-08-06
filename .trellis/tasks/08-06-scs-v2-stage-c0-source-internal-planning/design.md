# Technical design

## Boundary and evidence ceiling

Stage C.0 is a protocol-freeze task. It may reason from the accepted Stage B
receipts and object metadata, but it cannot inspect candidate content. A future
Stage C may produce source-internal candidate labels and provenance only. It
cannot establish vertical-datum truth, MRAR independence or model accuracy.

## Frozen data flow

```text
Stage B run (read-only)
  -> preflight hash/access verification
  -> authorized role-filtered reads
  -> derived temporary run
  -> parser adapter + source-internal QC labels
  -> sounding lineage
  -> exact cell x official_cruise aggregation
  -> independent verifier
  -> atomic immutable Stage C publication
```

The future output root is fixed:

```text
/mnt/data2/00-Data/ship/ncei/derived/scs_v2_sealed_confirmation/stage_c/<PROCESSING_RUN_ID>
```

The run ID must be a single safe segment matching
`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`, with no `..` or path separator.

## Object-role policy

| Stage B role/format | Initial Stage C permission | Purpose |
|---|---|---|
| `multibeam_data_compressed/.mb58.gz` | body read and derived-only decompression after authorization | sole primary sounding source |
| `navigation_sidecar/.fnv` | read after authorization | source-internal time/navigation cross-check only |
| `processing_sidecar/.inf` | read after authorization | format/count/metadata and direct datum-evidence search |
| `processing_sidecar/.fbt` | denied | duplicate derived bathymetry; no double counting or pseudo-independence |

Stage C must not glob the sealed directory. It reads the 768-row manifest and
opens only exact manifest paths whose role/format permission is active.

## Parser environment

The target parser identity is:

```text
MB-System tag:    5.8.3beta16
source commit:    1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422
MBIO format:      58 (MBF_EM710RAW)
```

The release is a pre-release and format 58 has recent upstream changes. The
tag is therefore necessary but not sufficient: a content-addressed OCI image
or equivalent immutable environment and an independent format-58 fixture
receipt are hard authorization inputs. The current host has no MB-System
executable and its Docker daemon is not accessible to the current user, so
actual Stage C is blocked at planning completion.

The future environment runs without network access, mounts the Stage B root
read-only at `/sealed`, and mounts only the new derived run root read-write at
`/derived`. Locale is `C.UTF-8`, timezone is `UTC`, and numeric output is
locale-independent. The manifest records kernel, container digest, compiler,
MB-System, libc, Python, numpy, pandas and pyarrow versions.

## Frozen command templates

Before each source read, the executor rehashes the sealed object and compares
it with the Stage B manifest. It then uses these exact command shapes, with
resolved paths supplied as argv rather than shell-expanded globs:

```bash
sha256sum -- <SEALED_MB58_GZ>
pigz -dc -- <SEALED_MB58_GZ> > <DERIVED_TMP_MB58>
mbinfo -I <DERIVED_TMP_MB58> -F58 -V
mblist -I <DERIVED_TMP_MB58> -F58 -P1 -L0 -MA -U3 '-OMN#XYzH'
mblist -I <DERIVED_TMP_MB58> -F58 -P1 -L0 -MA -U0 '-OMN#XYzH'
```

The `-U3` stream is the all-beam lineage stream with nulls represented as
NaN. The `-U0` stream is the native-valid subset. They are joined exactly by
`(source_object_sha256, parser_ping_index, beam_index)`. This yields a binary
`native_quality_state` without inventing an exact source quality code.
`depth_m_positive_down` is populated only from the native-valid stream;
flagged/null all-stream rows retain lineage keys but carry null depth, so a
flag encoding can never be mistaken for a signed bathymetric value.

The command contract assumes the documented meanings `M=Unix seconds`,
`N=ping count`, `#=beam number`, `X/Y=decimal-degree position`,
`z=positive-down meters`, and `H=heading`. Actual use is forbidden until the
exact pinned binary's `--help` snapshot and independent fixture prove the
field count, order, sign, unit, null and valid-subset behavior. Command output
must be captured without post-hoc column guessing.

No smoothing, ping averaging, speed filter, spatial filter, tide correction,
ray-tracing change, navigation merge, edit file, `mbprocess`, `mbclean`,
`mbareaclean` or `mbnavadjust` command is allowed.

## Field recovery

| Field | Recovery rule | Initial evidence state |
|---|---|---|
| `official_cruise_id` | exact Stage B manifest mapping | `verified_from_source_metadata` |
| source file | exact manifest relative path and SHA256 | `known` |
| time | fixture-verified parser `M`; UTC conversion only | nullable `known`, otherwise `officially_unknown` |
| line | direct source record/metadata only | `officially_unknown` |
| parser ping index | parser `N`, scoped to source object | nullable `known` |
| native ping ID | direct raw field only | `officially_unknown` |
| longitude/latitude | parser `X/Y`, numeric normalization only | nullable `known` |
| horizontal datum | direct source metadata only | `officially_unknown` |
| parser beam index | parser `#`, scoped to ping | nullable `known` |
| native beam ID | direct raw field only | `officially_unknown` |
| heading | parser `H` | nullable `known` |
| native validity | membership in pinned `-U0` output | `known` |
| exact quality code | direct parser/source field only | `officially_unknown` |
| depth | parser `z`, fixture-proven meters positive-down | nullable `known` |
| vertical datum | direct official/raw statement only | `officially_unknown` until proven |

Filename timestamps and stems remain filename metadata. They are never used to
fill time, line, ping, datum or quality fields.

## Fixture oracle

Fixture testing occurs before the container receives the Stage B mount. It has
two independent layers:

1. a synthetic adapter fixture with hand-specified tabular parser outputs,
   exercising longitude normalization, UTC conversion, sign, meters, NaN,
   zero, duplicate keys and valid/all membership;
2. a non-candidate format-58 golden fixture with an independently documented
   sounding/beam oracle and SHA256, exercising the pinned MB-System binary.

The second fixture cannot be produced by the same parser invocation being
tested. Its expected values must be hand-derived from the fixture generator or
an upstream regression oracle. Round-trip agreement through MB-System alone is
insufficient. Every expected value and tolerance is frozen in
`research/fixture-contract.yaml`.

## QC architecture

QC has three states:

```text
hard_pass
hard_fail
review
```

Hard failures are structural or native-quality failures and are excluded only
from cell aggregation; their sounding lineage rows remain. Review flags are
diagnostic and never alter aggregation eligibility. Thresholds are fixed in
`research/source-internal-qc.yaml` and cannot be changed after a candidate
depth has been opened.

This deliberately excludes a global 3STD rule. A whole-cruise or whole-line
distribution can mix real slopes, trenches and depth regimes; source-internal
review instead uses native validity and local ping/order context, while
retaining every observation and exact reason.

## Exact aggregation

Coordinates are assigned to the existing one-arc-minute grid:

```text
lon_bin = floor((lon_deg + 180) * 60)
lat_bin = floor((lat_deg + 90) * 60)
cell_id = "1min_<lat_bin>_<lon_bin>"
lon_center = -180 + (lon_bin + 0.5) / 60
lat_center =  -90 + (lat_bin + 0.5) / 60
```

Only `qc_eligible_for_cell=true` beams enter the numeric aggregate. The group
key is exactly `(cell_id, official_cruise_id)`. Median, quantiles, NMAD,
min/max/range and mean are computed from the individual beam depths in each
group. Batch size, input file order and worker count must yield identical
canonical row and numeric digests.

Cells with multiple cruises retain multiple rows and a separate contributor
table. No final pooled depth, cruise weighting or estimator selection occurs
in Stage C.

## Verification and publication

The producer writes to `<PROCESSING_RUN_ID>.tmp-*`; an error writes a
`failed_processing` receipt outside the authoritative namespace. The
independent verifier reopens sounding and aggregate Parquets, recomputes
schemas, counts, grid IDs, exact group statistics, input/object hashes,
held-out roles and forbidden-reference guards. Only `verification.json` with
`status=pass` permits atomic publication of the immutable run.

The verifier also compares Stage B file hashes, size, mode, mtime and inode
snapshots before and after processing. Any change blocks publication.

## Stop conditions

Stop before candidate body read if any input, authorization, parser,
environment, command, fixture, QC, schema or verifier hash differs.

Stop without publishing a candidate-ready run if any primary `.mb58.gz`
object fails decompression/parsing, any parser key is non-unique, a field count
drifts, source objects change, exact aggregation is not invariant, a required
cruise has zero eligible soundings, or a forbidden product/model/training
reference appears.

Unknown time, line, exact quality code, horizontal datum or vertical datum is
not silently repaired. It is an explicit output state and may limit later
evaluation without making source-internal extraction itself fail.
