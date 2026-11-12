"""Compare scratch streaming products with the retained 10-25 products."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

SCRATCH = Path('ncei/derived/swath_rebuild_check')
REFERENCE = Path('ncei/derived/processing_revision_20261025/swath')


def compare(label, new, old):
    left, right = pd.read_parquet(new), pd.read_parquet(old)
    columns = [name for name in left if name in right]
    changed = {}
    rows = np.zeros(len(left), dtype=bool)
    for name in columns:
        mismatch = ~(left[name].eq(right[name]) | (left[name].isna() & right[name].isna()))
        if mismatch.any():
            changed[name] = int(mismatch.sum())
        rows |= mismatch
    new_schema, old_schema = pq.read_schema(new), pq.read_schema(old)
    result = dict(label=label, new=str(new), old=str(old), new_rows=len(left), old_rows=len(right),
                  different_rows=int(rows.sum()), different_columns=changed,
                  new_only_columns=sorted(set(left) - set(right)),
                  old_only_columns=sorted(set(right) - set(left)),
                  dtype_differences={name: [str(new_schema.field(name).type), str(old_schema.field(name).type)]
                                     for name in columns if new_schema.field(name).type != old_schema.field(name).type})
    if label == 'NT05-06 points':
        a, b = pq.read_table(new), pq.read_table(old)
        result['arrow_null_count_differences'] = {name: [a[name].null_count, b[name].null_count]
                                                  for name in columns if a[name].null_count != b[name].null_count}
    print(json.dumps(result), flush=True)
    return result


def main():
    cases = [
        ('NT05-06', 'reference_final', 'first_batch', 'nt05-06__mb84'),
        ('HNRO05RR', 'hnro05rr_numeric', 'navigation_affected_extension', 'hnro05rr__mb41'),
        ('HNRO05RR', 'reference_final', 'navigation_review_hnro05rr', 'hnro05rr__mb41'),
        ('HNRO07RR', 'reference_final', 'navigation_review', 'hnro07rr__mb41'),
    ]
    results = [compare(f'{cruise} {run}', SCRATCH / run / 'cells_1min' / f'{cruise}.parquet',
                       REFERENCE / old / cruise / 'file_cells_1min' / f'{stem}.parquet')
               for cruise, run, old, stem in cases]
    results.append(compare('NT05-06 points', SCRATCH / 'points/points_checked/NT05-06.parquet',
                           REFERENCE / 'first_batch/NT05-06/points_checked/nt05-06__mb84.parquet'))
    new = pd.read_parquet(SCRATCH / 'reference_final/files.parquet').query("cruise == 'NT05-06'")
    old = pd.read_parquet(REFERENCE / 'first_batch/NT05-06/extraction_manifest.parquet')
    files = new.merge(old, on='filekey', how='outer', validate='one_to_one', indicator=True)
    results.append(dict(label='NT05-06 per-file counts', rows=len(files), unmatched=int((files._merge != 'both').sum()),
                        changed_ordinals=int((files.file_ordinal_x != files.file_ordinal_y).sum()),
                        changed_counts=int((files.n_selected != files.n_selected_basic_native_good_valid_ping_navigation).sum())))
    (SCRATCH / 'comparison.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
