"""Measure a scratch reconstruction's wall time and temporary disk use."""

import json
import subprocess
import sys
import resource
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from _common.file_io import atomic_write_text


def main():
    name, workers, *cruises = sys.argv[1:]
    root = Path('ncei/derived/swath_rebuild_check')
    output = root / name
    command = [sys.executable, '-u', '-m', 'ncei.swath', 'run', '--cruises', *cruises,
               '--output-root', str(output), '--workers', workers]
    start = time.monotonic()
    peak = peak_rss = peak_cpu = 0
    previous = {}
    previous_at = None
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    with (root / f'{name}.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        parent = psutil.Process(process.pid)
        while process.poll() is None:
            now = time.monotonic()
            current = {}
            rss = 0
            for item in [parent, *parent.children(recursive=True)]:
                try:
                    with item.oneshot():
                        cpu = item.cpu_times()
                        current[(item.pid, item.create_time())] = cpu.user + cpu.system
                        rss += item.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
            if previous_at is not None:
                delta = sum(seconds - previous.get(key, 0) for key, seconds in current.items())
                peak_cpu = max(peak_cpu, delta / (now - previous_at))
            previous, previous_at = current, now
            peak_rss = max(peak_rss, rss)
            size = 0
            for path in (output / '_tmp').rglob('*'):
                try:
                    if path.is_file() and not path.is_symlink():
                        size += path.stat().st_size
                except FileNotFoundError:
                    pass
            peak = max(peak, size)
            time.sleep(0.2)
    finished = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds = finished.ru_utime - usage.ru_utime + finished.ru_stime - usage.ru_stime
    record = dict(command=command, cruises=cruises, workers=int(workers), returncode=process.returncode,
                  wall_seconds=time.monotonic() - start, temporary_peak_bytes=peak, sample_seconds=0.2,
                  cpu_seconds=cpu_seconds, cpu_peak_cores=peak_cpu, process_tree_peak_rss_bytes=peak_rss)
    atomic_write_text(json.dumps(record, indent=2) + '\n', root / f'{name}_measurement.json')
    print(record)
    return process.returncode


if __name__ == '__main__':
    raise SystemExit(main())
