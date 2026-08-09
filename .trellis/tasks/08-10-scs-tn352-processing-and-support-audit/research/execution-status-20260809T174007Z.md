# Execution status: 20260809T174007Z

## Phase A

Status: `pass`

Accepted output:

```text
ncei/derived/scs_tn352_processing_and_support_audit/20260809T174007Z/phase_a
```

- classification: `B. official_raw_source_development_label`
- output role: `development_only_not_confirmation`
- four-cruise soundings / eligible / candidates:
  `59,298,192 / 51,303,876 / 3,549`
- TN352 soundings / eligible / candidates:
  `19,574,784 / 17,211,316 / 3,538`
- TN352 SCS soundings / eligible / candidates:
  `13,782,014 / 12,351,039 / 2,368`
- object 0168: `96,768` recovered soundings, `86,184` eligible,
  `198` H03 rows, `10` added cells, and `20` changed common-cell
  exact medians
- Phase A verification SHA256:
  `6cbbb74a7843df484323ea62eb27492af60e43c4ebea94aa6621c707fb11adfa`
- Phase A manifest SHA256:
  `68d0b88ca44b86fd649d95e72610d4c6f35cfaa6891da3af99faa7afa27de240`

The first producer run, `20260809T173725Z`, is retained with a failed verifier
receipt caused by a Markdown whitespace check in the verifier. It did not read
MRAR depth. The verifier check was corrected and the complete producer and
verifier sequence was repeated under the accepted run ID above.

## Phase B freeze

Status: `failed_count_gate_before_depth_access`

Failure evidence:

```text
ncei/derived/scs_tn352_processing_and_support_audit/
  20260809T174007Z.failed/phase_b/freeze_failure_receipt.json
```

- expected common cells: `2,244`
- observed common cells: `2,367`
- TN352 SCS candidate cells: `2,368`
- TN352 cells absent from the MRAR label and checked-point identity sets:
  `1min_6739_18005`
- MRAR label cells in the SCS rectangle: `168,769`
- MRAR basic-pass checked points in the SCS rectangle: `2,896,011`
- MRAR basic-pass checked-point cells in the rectangle: `168,769`
- MRAR label intersection with TN352: `2,367`
- MRAR checked-point identity intersection with TN352: `2,367`
- freeze failure receipt SHA256:
  `665f7bcc07ffd41b7ebef2aa6e27d9d633e4ab6f98671f1b55583aeecf9963d5`

The identity-only follow-up read `cell_id`, coordinates, track identity, and
`point_check_pass_basic`; it did not open either source's depth value. All
2,367 intersecting MRAR labels have `branch_role=regional_experiment`,
`sensitivity_only_flag=true`, `manual_review_any=false`, one track, and 1 to
30 passing points. These fields do not supply a registered selector that
explains a 2,244-cell cohort.

## Access and execution boundary

- MRAR/TN352 depth value reads for Phase B: `0`
- depth-difference reads: `0`
- mutual-nearest matching: `not_executed`
- GGM / PINN / GEBCO / product or model residual comparisons: `0`
- sealed object and sidecar body reads by this audit: `0`
- Stage C mutation: `0`

## Required decision

Do not change the expected count to 2,367 merely to pass the gate. The default
next action is to locate the non-depth lineage or exact cell-ID list that
defines the stated 2,244 cells. If 2,244 has no retained provenance and the
intended cohort is the intersection of the current registered inputs, a new
protocol version may set the expected count to 2,367 after separate user
approval. Phase B must use a new run and repeat the freeze process.
