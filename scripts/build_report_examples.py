"""Build report examples directly from the three published sample files.

Standard library creates JSON/Markdown; --plot additionally needs matplotlib.
No benchmark data, labels, splits, or scoring implementation are changed.
"""
import argparse
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'sgsc': 'benchmark/v1/examples/sgsc.json',
    'iflex': 'benchmark/v1/examples/iflex.json',
    'lirneasia': 'extensions/lirneasia_history_v1/examples/lirneasia.json',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    out = ROOT / 'docs/report_examples'
    out.mkdir(parents=True, exist_ok=True)
    records, originals = {}, {}
    for source, relative in FILES.items():
        raw = (ROOT / relative).read_bytes()
        sample = json.loads(raw)
        originals[source] = sample
        history = sample['input']['history']
        target = sample['output']['energy_kwh']
        records[source] = {
            'source_file': relative, 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'sample_id': sample['sample_id'],
            'profile': sample['input']['profile'],
            'history_start': history['start'], 'history_end': history['end'],
            'history_points': len(history['energy_kwh']),
            'history_first_four_kwh': history['energy_kwh'][:4],
            'context': sample['input']['context'],
            'target_points': len(target), 'target_first_four_kwh': target[:4],
            'target_total_kwh': sum(target),
            'strategy_label_present': False,
        }
        assert len(history['energy_kwh']) == 7 * len(target)
    sample = originals['lirneasia']
    with gzip.open(ROOT / 'extensions/lirneasia_history_v1/sources/cumulative_runs.jsonl.gz', 'rt') as f:
        for line in f:
            run = json.loads(line)
            if run['household_id'] != sample['metadata']['household_id']:
                continue
            offset = int((datetime.fromisoformat(sample['input']['history']['start']) - datetime.fromisoformat(run['start'])).total_seconds() / 900)
            if 0 <= offset and offset + 768 < len(run['import_register_kwh']):
                registers = run['import_register_kwh'][offset:offset + 769]
                energies = [b-a for a,b in zip(registers,registers[1:])]
                assert energies == sample['input']['history']['energy_kwh'] + sample['output']['energy_kwh']
                records['lirneasia']['first_history_registers_kwh'] = registers[:5]
                records['lirneasia']['first_target_registers_kwh'] = registers[672:677]
                records['lirneasia']['all_768_differences_exactly_match'] = True
                break
        else:
            raise AssertionError('Matching source cumulative run not found')
    (out / 'verified_examples.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(3, 1, figsize=(12, 8), constrained_layout=True)
        for ax, (source, sample) in zip(axes, originals.items()):
            h = sample['input']['history']
            step = h['interval_minutes'] / 60
            hist = h['energy_kwh']; target = sample['output']['energy_kwh']
            ax.stairs([v/step for v in hist], [(j-len(hist))*step for j in range(len(hist)+1)], color='#31688e', linewidth=0.8, label='Observed history (input)')
            ax.stairs([v/step for v in target], [j*step for j in range(len(target)+1)], color='#d66b21', linewidth=1.1, label='Observed target (answer)')
            ax.axvline(0, color='#333333', linestyle='--', linewidth=0.8)
            ax.set_title(sample['sample_id'], loc='left', fontsize=11)
            ax.set_ylabel('Interval mean kW')
            ax.set_xlim(-168,24); ax.grid(alpha=0.18)
            ax.legend(loc='upper left', fontsize=8)
        axes[-1].set_xlabel('Hours relative to forecast origin (source clock)')
        fig.suptitle('Three actual benchmark examples | measured values, no model predictions', fontsize=13)
        fig.savefig(out / 'measured_examples.png', dpi=160)
        plt.close(fig)
    print(json.dumps({k: {'sample_id': v['sample_id'], 'target_total_kwh': v['target_total_kwh']} for k,v in records.items()}))


if __name__ == '__main__':
    main()
