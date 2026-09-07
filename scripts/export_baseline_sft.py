"""Render baseline observations as SFT candidates; does not run a model or certify input availability."""
import argparse
import csv
import json
from pathlib import Path
from baseline_windows import ROOT
from build_baseline import read, render, writer


def export(root, destination, split):
    with (root / 'splits/household_holdout.csv').open() as f:
        selected = {r['sample_id'] for r in csv.DictReader(f) if split == 'all' or r['split'] == split}
    count = 0
    with writer(destination) as write:
        for source in ('sgsc', 'iflex'):
            for sample in read(root / 'data' / (source + '.jsonl.gz')):
                if sample['sample_id'] in selected:
                    row = render(sample)
                    assert json.loads(row['messages'][1]['content']) == sample['input']
                    assert json.loads(row['messages'][2]['content']) == sample['output']
                    write(row)
                    count += 1
    assert count == len(selected)
    print(json.dumps({'records': count, 'split': split, 'output': str(destination),
                      'status': 'rendered_observation_candidates', 'formal_training_release': False,
                      'training_executed': False}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT / 'baseline/v1')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--split', choices=['train', 'validation', 'test', 'all'], default='all')
    args = p.parse_args()
    export(args.root, args.output, args.split)
