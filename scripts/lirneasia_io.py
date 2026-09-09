"""Read or score the independent LIRNEasia extension; never run model training."""
import argparse
import copy
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path
from build_lirneasia_extension import DEFAULT

VARIANTS = ('history_only', 'history_profile')


def read_samples(split=None, root=DEFAULT):
    if split not in (None, 'train', 'validation', 'test'):
        raise ValueError('Unknown split')
    with gzip.open(Path(root) / 'data/lirneasia.jsonl.gz', 'rt') as f:
        for line in f:
            r = json.loads(line)
            if split is None or r['metadata']['split'] == split:
                yield r


def model_input(sample, variant='history_profile'):
    if variant not in VARIANTS:
        raise ValueError('Unknown input variant')
    r = copy.deepcopy(sample['input'])
    if variant == 'history_only':
        r.pop('profile')
    return r


def metrics(actual, predicted):
    if not isinstance(predicted, list) or len(predicted) != 96:
        raise ValueError('Expected 96 native 15min kWh values')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in predicted):
        raise ValueError('Invalid predicted value')
    a = [sum(actual[i:i+4]) for i in range(0, 96, 4)]
    p = [sum(predicted[i:i+4]) for i in range(0, 96, 4)]
    errors = [x-y for x, y in zip(p, a)]
    return {'hourly_mae_kw': sum(map(abs, errors)) / 24,
            'hourly_rmse_kw': math.sqrt(sum(v*v for v in errors) / 24),
            'daily_energy_absolute_error_kwh': abs(sum(predicted)-sum(actual)),
            'hourly_peak_absolute_error_kw': abs(max(p)-max(a)),
            'native_15min_mae_kw': sum(abs(x-y)*4 for x, y in zip(predicted, actual)) / 96}


def evaluate(predictions, split, variant, root=DEFAULT):
    if split not in ('validation', 'test') or variant not in VARIANTS:
        raise ValueError('Unsupported evaluation split or variant')
    opener = gzip.open if str(predictions).endswith('.gz') else open
    pred = {}
    with opener(predictions, 'rt') as f:
        for line in f:
            r = json.loads(line)
            if set(r) != {'sample_id', 'energy_kwh'} or type(r['sample_id']) is not str:
                raise ValueError('Expected exactly sample_id and energy_kwh')
            if r['sample_id'] in pred:
                raise ValueError('Duplicate prediction ID')
            pred[r['sample_id']] = r['energy_kwh']
    groups = defaultdict(list)
    expected = set()
    for s in read_samples(split, root):
        sid = s['sample_id']
        if sid in expected or sid not in pred:
            raise ValueError('Duplicate sample or missing prediction')
        expected.add(sid)
        groups[s['metadata']['household_id']].append(metrics(s['output']['energy_kwh'], pred[sid]))
    if not expected or expected != set(pred):
        raise ValueError('Empty set or extra prediction IDs')
    names = next(iter(groups.values()))[0]
    result = {k: sum(sum(m[k] for m in rows) / len(rows) for rows in groups.values()) / len(groups) for k in names}
    return {'source': 'lirneasia', 'split': split, 'samples': len(expected), 'households': len(groups),
            'input_variant_declared': variant, 'input_variant_verified_from_predictions': False,
            'metrics': result, 'aggregation': 'equal household, after within-household daily mean',
            'scope': 'separate screened day-ahead grid-import benchmark; no event-response metric'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=DEFAULT)
    p.add_argument('--predictions', type=Path, required=True)
    p.add_argument('--split', choices=['validation', 'test'], required=True)
    p.add_argument('--variant', choices=VARIANTS, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    r = evaluate(a.predictions, a.split, a.variant, a.root)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(r, indent=2, allow_nan=False)+'\n')
    print(json.dumps(r, indent=2))
