"""Read self-contained baseline household-day records, optionally by frozen household split."""
import argparse
import csv
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_samples(source, split=None, root=None):
    root = Path(root) if root else ROOT / 'baseline/v1'
    if source not in ('sgsc', 'iflex'): raise ValueError(source)
    selected = None
    if split is not None:
        if split not in ('train', 'validation', 'test'): raise ValueError(split)
        with (root / 'splits/household_holdout.csv').open() as f:
            selected = {x['sample_id'] for x in csv.DictReader(f) if x['source'] == source and x['split'] == split}
    with gzip.open(root / 'data' / (source + '.jsonl.gz'), 'rt') as f:
        for line in f:
            sample = json.loads(line)
            if selected is None or sample['sample_id'] in selected: yield sample


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', choices=['sgsc', 'iflex'], default='sgsc')
    p.add_argument('--split', choices=['train', 'validation', 'test'])
    args = p.parse_args()
    r = next(read_samples(args.source, args.split))
    print(json.dumps({'sample_id': r['sample_id'], 'profile_modules': list(r['input']['profile']),
                      'history_points': len(r['input']['history']['energy_kwh']),
                      'target_points': len(r['output']['energy_kwh']), 'unit': 'kWh',
                      'formal_training_release': r['metadata']['formal_training_release']}, ensure_ascii=False, indent=2))
