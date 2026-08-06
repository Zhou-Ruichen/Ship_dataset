# Stage C.0 tool availability

## Local inventory

Checked from repository root on 2026-08-06 without opening a sealed object:

| Tool | State | Version/evidence |
|---|---|---|
| MB-System `mbinfo` | missing | not on `PATH` |
| MB-System `mblist` | missing | not on `PATH` |
| MB-System `mbnavlist` | missing | not on `PATH` |
| MB-System `mbdump` | missing | not on `PATH` |
| `gzip` | available | Debian/Ubuntu package `1.12-1ubuntu3.2` |
| `pigz` | available | Debian/Ubuntu package `2.8-1` |
| Python | available | `3.12.10` |
| numpy | available | `2.2.6` |
| pandas | available | `2.2.3` |
| pyarrow | available | `24.0.0` |
| scipy | available | `1.15.3` |
| Docker client | available | `29.1.3` |
| Docker engine | unavailable to current user | permission denied on `/var/run/docker.sock` |

The repository contains no existing `.mb58`, `.fbt` or `.fnv` parser. Stage C
is therefore `blocked_tool_and_fixture_not_ready`; implementing an ad hoc
binary parser is not an allowed fallback.

## Frozen target

The candidate parser is MB-System tag `5.8.3beta16`, source commit
`1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422`, with MBIO format 58. The
official project release history identifies format 58 as `MBF_EM710RAW` and
shows recent format-58 changes, so the pre-release tag alone is not sufficient
evidence of correct sign/reference handling.

Authoritative references consulted:

- [MB-System releases](https://github.com/dwcaress/MB-System/releases)
- [MBARI MB-System documentation](https://www.mbari.org/technology/mb-system/documentation/)
- [MB-System mblist manual](https://www.ldeo.columbia.edu/res/pi/MB-System/mbweb/tmp/old5.0.beta/html5/mblist.html)

The manual documents `z` as depth in meters positive downward, `Z` as
positive-up topography, `M` as decimal Unix time, `N` as ping count, `#` as
beam number, and `X/Y` as decimal-degree longitude/latitude. Because the
online mblist manual is historical rather than the pinned binary's generated
manual, these meanings are treated as fixture hypotheses until the exact
binary help and independent golden fixture both pass.

## Authorization consequence

The inactive authorization template deliberately leaves these fields
unresolved:

```text
parser_environment_digest
parser_help_snapshot_sha256
format58_fixture_bytes_sha256
format58_fixture_oracle_sha256
fixture_verification_sha256
producer_sha256
verifier_sha256
stage_c0_planning_commit
```

Stage C cannot be authorized while any is blank or placeholder-valued.
