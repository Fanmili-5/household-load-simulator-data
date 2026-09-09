"""Optional full-cohort reconstruction from the eight original survey CSVs and meter CSV.

Requires the DuckDB CLI on PATH. Raw CSVs must be placed together in --raw-root.
The public excerpt builder does not require these large raw files or DuckDB.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from build_lirneasia_extension import ROOT, DEFAULT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be a new directory')
    if any(a.output.resolve().is_relative_to((ROOT / k).resolve()) for k in ('benchmark', 'baseline', 'extensions')):
        p.error('Raw audit must use a separate output directory')
    evidence = json.loads((DEFAULT / 'provenance/source_integrity.json').read_text())
    inputs = {r['filename']: r['sha256'] for r in evidence['survey_members']}
    inputs['smart_15min_2.csv'] = evidence['raw_meter_member']['sha256']
    for name, expected in inputs.items():
        h = hashlib.sha256()
        with (a.raw_root / name).open('rb') as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
                h.update(chunk)
        if h.hexdigest() != expected:
            raise ValueError('Original source hash mismatch: ' + name)
    executable = shutil.which('duckdb')
    if executable is None:
        p.error('DuckDB CLI is required for full raw-cohort reconstruction')
    sql = (DEFAULT / 'provenance/full_cohort_audit.sql').read_text()
    sql = sql.replace('@RAW@', str(a.raw_root.resolve()).replace("'", "''"))
    a.output.mkdir(parents=True)
    subprocess.run([executable, ':memory:', '-bail'], input=sql, text=True, cwd=a.output, check=True)
    print((a.output / 'strict_counts.json').read_text())


if __name__ == '__main__':
    main()
