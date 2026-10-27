import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
import tempfile

def load(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        if path.suffix == '.csv':
            rows = list(csv.DictReader(f))
        elif path.suffix == '.jsonl':
            rows = [json.loads(line) for line in f if line.strip()]
        else:
            rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError(f'{path}: expected a list of records')
    result = {}
    for row in rows:
        key = row.get('id')
        if not isinstance(key, str) or not key:
            raise ValueError(f'{path}: missing or invalid id')
        if key in result:
            raise ValueError(f'{path}: duplicate id {key}')
        result[key] = row
    return result


def number(value):
    if value is None or value.strip().lower() in ('', 'nan', 'na', 'null', 'none'):
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f'Non-numeric feature: {value!r}') from exc
    if not math.isfinite(result):
        raise ValueError(f'Non-finite feature: {value!r}')
    return int(result) if result.is_integer() else result


def extract(args):
    root = args.data_dir.resolve()
    dataset = load(root / 'dataset.jsonl')
    answers = load(root / 'answers.jsonl')
    evaluations = load(root / 'answers_eval.jsonl')
    features = load(root / 'features.csv')
    domains = load(root / 'question_domains.json')
    for name, table in [('answers', answers), ('evaluations', evaluations),
                        ('features', features), ('domains', domains)]:
        extra = table.keys() - dataset.keys()
        if extra:
            raise ValueError(f'{name}: {len(extra)} unknown ids; example {sorted(extra)[0]}')
        print(f'{name}: {len(dataset.keys() - table.keys())} missing records', file=sys.stderr)
    models = sorted({k[:-7] for table in (answers, evaluations)
                     for row in table.values() for k in row if k.endswith('-answer')})
    if args.list_models:
        print('\n'.join(models))
        return
    selected = args.models or models
    if len(selected) != len(set(selected)):
        raise ValueError('Repeated model names')
    unknown = set(selected) - set(models)
    if unknown:
        raise ValueError(f'Unknown models: {sorted(unknown)}; available: {models}')
    if not args.output:
        raise ValueError('--output is required unless using --list-models')
    output = args.output.resolve()
    inputs = [root / n for n in ('dataset.jsonl', 'answers.jsonl', 'answers_eval.jsonl',
                                'features.csv', 'question_domains.json')]
    if output in inputs:
        raise ValueError('Output must not replace a release input')
    if output.exists() and not args.overwrite:
        raise ValueError('Output exists; use --overwrite to replace it')
    wanted = set(args.ids) if args.ids else None
    if wanted and wanted - dataset.keys():
        raise ValueError(f'Unknown ids: {sorted(wanted - dataset.keys())[:5]}')
    records = []
    for key, base in dataset.items():
        if wanted is not None and key not in wanted:
            continue
        if args.split and base.get('split') not in args.split:
            continue
        a, e, f, d = (table.get(key, {}) for table in (answers, evaluations, features, domains))
        # Reject conflicting copies rather than silently pairing the wrong judgment/answer.
        for other in (a, e, d):
            for field in ('question', 'gold', 'target', 'split', 'sparql'):
                if field in base and field in other and base[field] != other[field]:
                    raise ValueError(f'{key}: conflicting {field}')
        if not d.get('sparql') and not base.get('sparql'):
            raise ValueError(f'{key}: no SPARQL query available')
        row = dict(base)
        row['sparql'] = d.get('sparql') or base['sparql']
        row['source_id'] = f.get('source_id') or None
        row['features'] = {k: number(v) for k, v in f.items() if k not in ('id', 'source_id')} if f else None
        row['domain'] = {k: v for k, v in d.items() if k not in ('id', 'question', 'sparql')} if d else None
        row['models'] = {}
        for model in selected:
            field = model + '-answer'
            if field in a and field in e and a[field] != e[field]:
                raise ValueError(f'{key}/{model}: answer differs between files')
            answer = a.get(field, e.get(field))
            gpt = e.get('eval_' + model)
            claude = e.get('claude_eval_' + model)
            if answer is None and (gpt is not None or claude is not None):
                raise ValueError(f'{key}/{model}: evaluation without answer')
            row['models'][model] = {'answer': answer, 'eval': gpt, 'claude_eval': claude}
        if args.complete_only and (row['features'] is None or
            any(v is None for v in row['features'].values()) or
            any(any(v is None for v in item.values()) for item in row['models'].values())):
            continue
        records.append(row)
    if not records:
        raise ValueError('No records match the filters')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix='.extract-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            if args.format == 'json':
                json.dump(records, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write('\n')
            else:
                for row in records:
                    handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Wrote {len(records)} records, {len(selected)} models to {output}', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / '10-2026')
    parser.add_argument('--list-models', action='store_true')
    parser.add_argument('--models', nargs='+', help='Exact model names from --list-models; default: all')
    parser.add_argument('--ids', nargs='+', help='Select question ids')
    parser.add_argument('--split', nargs='+', choices=['train', 'valid', 'val', 'test'])
    parser.add_argument('--complete-only', action='store_true', help='Require all features, answers and both judgments for selected models')
    parser.add_argument('--format', choices=['jsonl', 'json'], default='jsonl')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    try:
        extract(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
