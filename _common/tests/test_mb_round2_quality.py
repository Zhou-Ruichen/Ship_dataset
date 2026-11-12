"""Check streaming swath source identities, selection and cruise aggregation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from ncei.swath import aggregation, decode, exclusions, format_times, pipeline, points, selection, sources


def source(root: Path, fmt: int = 41, key: str = 'key') -> sources.Source:
    return sources.Source('TEST', root / 'source.gz', root, Path('TEST/source.gz'),
                          7, key, fmt, 'test fixture', 10)


def beams(depth=(2000., 10000., 0., 2000., 2500.)) -> pd.DataFrame:
    n = len(depth)
    return pd.DataFrame({
        'lon': [134.] * n, 'lat': [38.] * n, 'depth_raw': list(depth),
        'native_quality_state': ['good', 'flagged', 'null', 'unknown', 'good'][:n],
        'epoch_us': np.arange(n, dtype=np.int64) + 1_000_000,
        'native_ping_counter': np.arange(n, dtype=np.int64) + 1,
        'parser_ping_index': np.arange(n, dtype=np.int64),
        'beam_index': np.zeros(n, dtype=np.int32), 'ping_navigation_record_index': np.arange(n),
        'ping_lon': [134.] * n, 'ping_lat': [38.] * n,
        'valid_ping_navigation': [True] * n, 'ping_navigation_reason': ['valid'] * n,
    })


class StreamingSwathTest(unittest.TestCase):
    def test_quality_stages_and_exact_ping_exclusion(self):
        frame = beams()
        triples, counts = selection.grid_candidates(frame, {(4, 1_000_004, 5)})
        self.assertEqual(counts['positive'], dict(n_pass_basic=4, n_selected_basic_native_good=2,
                         n_selected_before_exclusions=2, n_excluded_selected_beams=1, n_selected=1))
        self.assertEqual(counts['n_excluded_beams'], 1)
        self.assertEqual(triples.depth_raw.tolist(), [2000.])
        self.assertFalse(selection.excluded_pings(frame, {(4, 1_000_003, 5)}).any())

    def test_depth_sign_is_cruise_wide_and_counts_zeros(self):
        frame = beams((-2400., -2500., 0., -2000., -3000.))
        triples, counts = selection.grid_candidates(frame, set())
        self.assertEqual(selection.depth_sign(counts), ('mixed_sign', 1))
        self.assertEqual(counts['positive']['n_selected'], 0)
        self.assertEqual(counts['negative']['n_selected'], 2)
        self.assertEqual(len(triples), 2)
        self.assertEqual(selection.depth_sign(selection.depth_counts(np.full(20, -1.))), ('mostly_negative', -1))

    def test_numeric_navigation_and_basic_depth(self):
        frame = beams()
        frame.loc[0, 'valid_ping_navigation'] = False
        frame.loc[4, 'depth_raw'] = 11500.1
        triples, counts = selection.grid_candidates(frame, set())
        self.assertEqual(counts['positive']['n_selected'], 0)
        self.assertEqual(counts['n_invalid_navigation_beams'], 1)
        self.assertTrue(triples.empty)

    def test_empty_beam_listing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'empty.tsv'
            path.touch()
            result = decode.read_beams(path, allow_null_depth=False)
            self.assertTrue(result.empty)

    def test_u0_exact_join_retains_native_good_with_invalid_navigation(self):
        all_beams = pd.DataFrame([
            ['1.000001', 1, 0, np.nan, 2., 100., 0.],
            ['1.000001', 1, 1, 1., 2., np.nan, 0.],
            ['2.000001', 1, 0, 1., 2., 110., 0.],
        ], columns=decode.BEAM_COLUMNS)
        good = all_beams.iloc[[0]].copy()
        nav = pd.DataFrame({
            'ping_navigation_record_index': [0, 1], 'epoch_us': [1_000_001, 2_000_001],
            'native_ping_counter': [1, 1], 'ping_lon': [0., 1.], 'ping_lat': [0., 2.],
            'valid_ping_navigation': [False, True], 'ping_navigation_reason': ['zero_navigation', 'valid'],
        })
        result = decode.join_beams(all_beams, good, nav)
        self.assertEqual(result.native_quality_state.tolist(), ['good', 'null', 'flagged'])
        self.assertTrue(np.isnan(result.loc[0, 'lon']))
        self.assertTrue(np.isnan(result.loc[0, 'lat']))
        self.assertEqual(result.parser_ping_index.tolist(), [0, 0, 1])
        with self.assertRaisesRegex(ValueError, 'duplicate U0'):
            decode.join_beams(all_beams, pd.concat([good, good]), nav)
        bad = good.copy()
        bad.loc[:, 'depth_raw'] = 101.
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            decode.join_beams(all_beams, bad, nav)

    def test_flat_ship_layouts_and_historical_file_keys(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw = root / 'raw'
            history = root / 'history'
            for directory in (raw / 'ship/TEST', raw / 'FLAT'):
                directory.mkdir(parents=True)
                (directory / 'source.mb41.gz').touch()
            (history / 'TEST').mkdir(parents=True)
            pd.DataFrame([{'relpath': 'TEST/source.mb41.gz', 'filekey': 'historical',
                           'file_ordinal': 19, 'mb_format': 41, 'format_note': 'suffix'}]).to_parquet(
                               history / 'TEST/extraction_manifest.parquet', index=False)
            directories = sources.cruise_directories([raw], {'TEST', 'FLAT'}, {'TEST', 'FLAT'})
            records = sources.discover('TEST', directories['TEST'], history)
            self.assertEqual((records[0].filekey, records[0].file_ordinal), ('historical', 19))
            flat = sources.discover('FLAT', directories['FLAT'], history)
            self.assertEqual(flat[0].filekey, sources.file_key(Path('FLAT/source.mb41.gz')))
            records[0].path.unlink()
            missing = sources.discover('TEST', directories['TEST'], history)
            self.assertFalse(missing[0].path.exists())
            self.assertEqual(missing[0].filekey, 'historical')

    def test_failed_supported_file_blocks_l2_and_batch_continues(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            bad = source(root)
            next_source = source(root, key='next')
            frame = beams()
            frame.attrs.update(ping_time_start_us=1_000_000, ping_time_end_us=1_000_004,
                               n_source_pings=5, n_invalid_navigation_pings=0)
            def mock_decode(record, _temp, _environment):
                if record.filekey == 'key':
                    raise ValueError('source failure')
                return frame
            directories = {'TEST': [root], 'NEXT': [root]}
            with patch.object(pipeline, 'discover', side_effect=[[bad], [next_source]]), \
                    patch.object(pipeline, 'decode', side_effect=mock_decode):
                self.assertEqual(pipeline.run(root, ['TEST', 'NEXT'], directories, {}, 1, False), 1)
            summary = pd.read_parquet(root / 'cruises.parquet').set_index('cruise')
            self.assertEqual(summary.loc['TEST', 'status'], 'failed')
            self.assertEqual(summary.loc['NEXT', 'status'], 'completed')
            self.assertFalse((root / 'cells_1min/TEST.parquet').exists())
            self.assertTrue((root / '_completed/NEXT').exists())
            self.assertFalse((root / '_tmp/NEXT').exists())
            with patch.object(pipeline, 'discover', side_effect=AssertionError('must skip')):
                self.assertEqual(pipeline.run(root, ['NEXT'], directories, {}, 1, True), 0)

    def test_shared_aggregation_preserves_duplicates_and_unique_median(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            frame = pd.DataFrame({'lon': [134.] * 3, 'lat': [38.] * 3, 'depth_raw': [100., 100., 300.]})
            shard = root / 'file.parquet'
            frame.to_parquet(shard, index=False)
            result = aggregation.aggregate_cruise([shard], root, root / 'cells.parquet', 'TEST', [41], 1, 3)
            cells = pd.read_parquet(root / 'cells.parquet')
            self.assertEqual(result['n_selected'], 3)
            self.assertEqual(cells.median_depth_m.iloc[0], 100.)
            self.assertEqual(cells.median_depth_m_unique_triples.iloc[0], 200.)
            self.assertEqual(cells.n_unique_triples.iloc[0], 2)
            self.assertEqual(len(cells.columns), 23)

    def test_checked_points_keep_ieee_nan_and_historical_version(self):
        frame = beams()
        with tempfile.TemporaryDirectory() as name:
            standard = points.checked_frame(frame, source(Path(name)), 10)
            table = points.checked_table(standard, 1, {})
        self.assertEqual(table['gobs'].null_count, 0)
        self.assertTrue(np.isnan(table['gobs'].to_numpy()).all())
        self.assertIn('exact source ping navigation', table['standardization_version'][0].as_py())
        self.assertEqual(table['point_index_in_track'].to_pylist(), list(range(10, 15)))

    def test_cell_partition_does_not_change_statistics(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            frame = pd.DataFrame({
                'lon': [130., 131., 130., 132., 131., 130., 132.], 'lat': [38.] * 7,
                'depth_raw': [100., 200., 100., 300., 250., 400., 350.],
            })
            for partition_rows, filename in [(40_000_000, 'one'), (2, 'many')]:
                shards = [root / 'first.parquet', root / 'second.parquet']
                frame.iloc[:4].to_parquet(shards[0], index=False)
                frame.iloc[4:].to_parquet(shards[1], index=False)
                with patch.object(aggregation, 'TARGET_PARTITION_ROWS', partition_rows):
                    aggregation.aggregate_cruise(shards, root, root / f'{filename}.parquet', 'TEST', [41], 1, len(frame))
            pd.testing.assert_frame_equal(pd.read_parquet(root / 'one.parquet'), pd.read_parquet(root / 'many.parquet'),
                                          check_exact=True)

    def test_format_interval_union_does_not_fill_gaps(self):
        left = format_times.interval_union([(0, 20), (10, 30), (50, 100)])
        right = [(35, 40), (60, 80)]
        self.assertEqual(left, [(0, 30), (50, 100)])
        self.assertEqual(format_times.interval_intersection(left, right), [(60, 80)])
        rows = [dict(mb_format=41, status='ok', n_rows=1, ping_time_start_us=0, ping_time_end_us=10),
                dict(mb_format=58, status='ok', n_rows=1, ping_time_start_us=10, ping_time_end_us=20)]
        summary = format_times.format_time_summary(rows)
        self.assertTrue(summary['format_overlaps'])
        self.assertEqual(summary['format_overlap_us'], 0)
        self.assertEqual(aggregation.source_labels([41, 58]), ('ncei_mb41_mb58', 'mb41_mb58'))

    def test_multiformat_overlap_stops_cruise_without_l2(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            records = [source(root, 41, 'first'), source(root, 58, 'second')]
            frame = beams()
            frame.attrs.update(ping_time_start_us=1_000_000, ping_time_end_us=1_000_004)
            with patch.object(pipeline, 'decode', return_value=frame):
                rows, summary = pipeline.process_cruise('TEST', records, root, {}, 1)
            self.assertEqual(summary['status'], 'format_overlap')
            self.assertEqual(summary['format_overlap_us'], 4)
            self.assertEqual(summary['formats'], [41, 58])
            self.assertFalse((root / 'cells_1min/TEST.parquet').exists())
            pipeline.checkpoint(root, rows, summary)
            self.assertFalse((root / '_completed/TEST').exists())
            self.assertFalse((root / '_tmp/TEST').exists())

    def test_points_subset_retains_whole_cruise_indices_and_sign(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            records = [source(root, 41, 'first'), source(root, 41, 'second')]
            frame = beams()
            with patch.object(points, 'decode', return_value=frame):
                points.write_points(records, root / 'points.parquet', {'second'}, [133, 37, 135, 39], {})
            result = pd.read_parquet(root / 'points.parquet')
            self.assertEqual(result.point_index_in_track.tolist(), list(range(5, 10)))
            self.assertEqual(result.point_index_in_file.tolist(), list(range(5)))
            self.assertEqual(set(result.filekey), {'second'})
            self.assertEqual(result[selection.SELECTION_COLUMN].sum(), 2)

    def test_mb84_requires_its_original_projection(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with self.assertRaises(FileNotFoundError):
                decode.prepare_input(source(root, 84), root)


if __name__ == '__main__':
    unittest.main()
