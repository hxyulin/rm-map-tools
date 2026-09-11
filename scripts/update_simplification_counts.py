#!/usr/bin/env python3
"""Render the documented preset tables from the retained measurement record."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tables():
    rows = json.loads((ROOT / 'benchmarks/2026-09-11-preset-inventory/samples.json').read_text())
    lines = ['Totals across the three sampled products. Visual and collision files are counted separately.', '',
             '| Preset | Output | Meshes | Primitives | Vertices | Triangles | GLB MB |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for preset in ('legacy', 'simulation', 'preview', 'vision'):
        selected = [row for row in rows if row['preset'] == preset]
        if len(selected) != 3 or len({row['part'] for row in selected}) != 3:
            raise ValueError(f'Expected three distinct product samples for {preset}')
        for kind in ('visual', 'collision'):
            total = {key: sum(row[kind][key] for row in selected) for key in ('meshes', 'primitives', 'vertices', 'triangles', 'glb_bytes')}
            values = ' | '.join(f'{total[key]:,}' for key in ('meshes', 'primitives', 'vertices', 'triangles'))
            lines.append(f'| `{preset}` | {kind} | {values} | {total["glb_bytes"] / 1e6:.2f} |')
    lines += ['', 'Triangle counts by source product:', '',
              '| Asset sample | Source product | Preset | Visual triangles | Collision triangles |',
              '| --- | --- | --- | ---: | ---: |']
    for row in rows:
        lines.append(f'| {row["asset"]} | `{row["part"]}` | `{row["preset"]}` | {row["visual"]["triangles"]:,} | {row["collision"]["triangles"]:,} |')
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    page = ROOT / 'docs/simplification-results.md'
    start, end = '<!-- BEGIN PRESET TABLES -->', '<!-- END PRESET TABLES -->'
    before, rest = page.read_text().split(start)
    _, after = rest.split(end)
    rendered = before + start + '\n' + tables() + '\n' + end + after
    if args.check:
        if rendered != page.read_text():
            raise SystemExit('Preset tables are stale. Run python3 scripts/update_simplification_counts.py')
        print('Preset tables match the retained measurements.')
    else:
        page.write_text(rendered)
