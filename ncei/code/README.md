# ncei/code — legacy download scripts (frozen)

This directory now holds only the legacy round-2 download scripts, kept in
place while the Tier-B loop runs:

- `41_tier_a_gapfill.py` — the downloader currently re-invoked by
  `/tmp/tierB_gapfill/supervise.sh` (platforms_tree inventory → diff →
  fetch → merge).
- `download_tier_a_round2.py` — the first tier-A downloader, superseded
  by 41.
- `41_gzip_preflight.py` — fail-closed `gzip -t` verification.
- `32_mb_round2_completeness.py` — completeness audit; its formal manifest
  is consumed by the swath census stage.

Their replacement is the unified downloader
`python -m ncei.download <command>` ([`ncei/download/README.md`](../download/README.md));
after the switchover (needs the user's go-ahead) these four scripts are
archived per `docs/code_archive.md`.

## Where the processing code went

- Trackline chain (stages 01–13, 23–26, 28, 30–31, 39–40):
  `python -m ncei.trackline <command>` (`ncei/trackline/`; stage numbers
  work as aliases).
- Round-2 swath chain (stages 33–37, 43): `python -m ncei.swath <command>`
  (`ncei/swath/`).
- Frozen analyses (Step 08 validation pack 14–22, network bias 27,
  interpolation holdout 29): `ncei/analysis/`.
- Download-value ranking (stage 38): `python -m ncei.download rank`.

Old `ncei/code/NN_*.py` paths in historical reports and manifests resolve
through the table in `docs/code_archive.md`.
