#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Share exact, unnamed geometric values and style definitions in a derived STEP.

Topology, products, occurrences, layers and style bindings keep their identities.
No floating point conversion, rounding, healing or tessellation enters matching.
Removed definition IDs remain resolvable through the output alias table. The
output is immutable source material for subsequent passes, not an editable model
with independently mutable copies of shared values.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time

import numpy as np
from audit_step import geometry_length_units
from cad_hierarchy import remap_record, verify_assembly_graph
from p21index import Index

GEOMETRIC_VALUES = {'CARTESIAN_POINT', 'DIRECTION', 'VECTOR'}
STYLE_VALUES = {'COLOUR_RGB', 'DRAUGHTING_PRE_DEFINED_COLOUR',
                'DRAUGHTING_PRE_DEFINED_CURVE_FONT', 'CURVE_STYLE',
                'FILL_AREA_STYLE_COLOUR', 'FILL_AREA_STYLE',
                'SURFACE_STYLE_FILL_AREA', 'SURFACE_SIDE_STYLE',
                'SURFACE_STYLE_USAGE', 'PRESENTATION_STYLE_ASSIGNMENT'}
# Placement axes are deliberately not interned. Their point/direction descendants
# are protected too when referenced outside geometric support definitions.
PLACEMENT_USERS = {'ITEM_DEFINED_TRANSFORMATION', 'SHAPE_REPRESENTATION',
                   'ADVANCED_BREP_SHAPE_REPRESENTATION',
                   'MANIFOLD_SURFACE_SHAPE_REPRESENTATION',
                   'GEOMETRICALLY_BOUNDED_SURFACE_SHAPE_REPRESENTATION',
                   'REPRESENTATION_MAP', 'CARTESIAN_TRANSFORMATION_OPERATOR_3D',
                   'CARTESIAN_TRANSFORMATION_OPERATOR_3DNON_UNIFORM'}


def profile(ix):
    """Count exact entity text and references; whitespace/header are separate."""
    stats = []
    for tid, name in enumerate(ix.typenames):
        rows = np.flatnonzero(ix.types == tid)
        stats.append({'type': name, 'records': len(rows),
                      'bytes': int(ix.lens[rows].sum()),
                      'references': int(ix.reference_spans(rows)[1].sum())})
    return {'bytes': ix.size, 'records': ix.n, 'references': ix.reference_count,
            'types': sorted(stats, key=lambda s: -s['bytes'])}


def plan_sharing(ix):
    """Return exact aliases and evidence without altering the indexed source."""
    units = geometry_length_units(ix)
    if len(units) != 1 or 'non-SI' in units:
        raise ValueError('sharing requires one explicit SI geometry length unit')
    protected = set()
    # A name or direct style/layer binding gives a value its own semantic identity.
    for row in ix.rows_of('PRESENTATION_LAYER_ASSIGNMENT', 'PRESENTATION_LAYER_USAGE'):
        protected.update(map(int, ix.refs_of(int(row))))
    for row in ix.rows_of('STYLED_ITEM', 'OVER_RIDING_STYLED_ITEM'):
        refs = ix.refs_of(int(row))
        # Overriding items append their overridden binding after the target.
        # Assignment definitions are reusable; bindings/targets stay independent.
        if len(refs):
            offset = -2 if ix.tname(int(row)) == 'OVER_RIDING_STYLED_ITEM' else -1
            protected.add(int(refs[offset]))
    stack = []
    for row in ix.rows_of(*PLACEMENT_USERS):
        for ref in ix.refs_of(int(row)):
            r = ix.r(int(ref))
            if r >= 0 and ix.tname(r) in GEOMETRIC_VALUES | {'AXIS2_PLACEMENT_3D', 'AXIS2_PLACEMENT_2D', 'AXIS1_PLACEMENT'}:
                stack.append(int(ref))
    placement_seen = set()
    while stack:
        eid = stack.pop()
        if eid in placement_seen:
            continue
        placement_seen.add(eid)
        row = ix.r(eid)
        if row < 0:
            raise ValueError(f'unresolved placement #{eid}')
        protected.add(eid)
        stack.extend(map(int, ix.refs_of(row)))

    eligible = set()
    for row in ix.rows_of(*(GEOMETRIC_VALUES | STYLE_VALUES)):
        row = int(row); eid = int(ix.ids[row])
        # Styles preserve every literal name. Geometric values need an empty
        # display name; named points/directions may be CAD construction handles.
        if eid not in protected and (ix.tname(row) in STYLE_VALUES or
                                      re.match(rb"\s*''\s*,", ix.args(row))):
            eligible.add(eid)
    aliases = {}; representatives = {}; visited = set(); visiting = set()

    def canonical(eid):
        if eid not in eligible or eid in visited:
            return aliases.get(eid, eid)
        if eid in visiting:
            raise ValueError(f'cyclic value/style graph at #{eid}')
        visiting.add(eid)
        row = ix.r(eid)
        for ref in ix.refs_of(row):
            child = int(ref)
            if ix.r(child) < 0:
                raise ValueError(f'unresolved definition #{child}')
            canonical(child)
        rhs = remap_record(ix.text(row).split(b'=', 1)[1], aliases)
        # Full bytes are the key, not a lossy float tuple or digest alone.
        representative = representatives.setdefault(rhs, eid)
        if representative != eid:
            aliases[eid] = representative
        visiting.remove(eid); visited.add(eid)
        return representative

    for eid in sorted(eligible):
        canonical(eid)
    counts = Counter(ix.tname(ix.r(eid)) for eid in aliases)
    return aliases, {'geometry_length_units': units,
                     'protected_value_or_binding_ids': len(protected),
                     'protected_placement_ids': len(placement_seen),
                     'eligible_definitions': len(eligible),
                     'removed_by_type': dict(sorted(counts.items()))}


def _rewritten(ix, row, aliases, redirected):
    refs = ix.refs_of(row)
    return (remap_record(ix.text(row), aliases) if len(refs) and redirected[refs].any()
            else ix.text(row))


def write_shared(ix, aliases, destination):
    """Preserve all non-entity bytes and retained IDs, rewriting references only."""
    redirected = np.zeros(ix.max_id + 1, dtype=bool)
    redirected[list(aliases)] = True
    pos = 0
    with Path(destination).open('wb') as output:
        for row in range(ix.n):
            start = int(ix.starts[row]); end = start + int(ix.lens[row])
            output.write(ix.mm[pos:start])
            if int(ix.ids[row]) not in aliases:
                output.write(_rewritten(ix, row, aliases, redirected))
            pos = end
        output.write(ix.mm[pos:])


def validate_shared(source, shared, aliases):
    """Prove every removed definition exact and every retained record rewritten only.

    The independent reparse checks all references resolve and all retained IDs
    match, including every face, edge, product, occurrence and presentation target.
    """
    expected_aliases, _ = plan_sharing(source)
    if aliases != expected_aliases:
        raise ValueError('aliases do not match protected exact-sharing policy')
    redirected = np.zeros(source.max_id + 1, dtype=bool)
    redirected[list(aliases)] = True
    if shared.n != source.n - len(aliases):
        raise ValueError('unexpected retained entity count')
    if len(shared.refs) and (shared.refs.max() > shared.max_id or
                             (shared.row[shared.refs] < 0).any()):
        raise ValueError('unresolved output reference')
    expected_bytes = hashlib.sha256(); pos = 0
    for row in range(source.n):
        eid = int(source.ids[row])
        start = int(source.starts[row])
        expected_bytes.update(source.mm[pos:start])
        pos = start + int(source.lens[row])
        if eid in aliases:
            other = aliases[eid]
            if other in aliases or other == eid or source.r(other) < 0:
                raise ValueError('aliases must resolve directly to retained source IDs')
            lhs = remap_record(source.text(row).split(b'=', 1)[1], aliases)
            rhs = remap_record(source.text(source.r(other)).split(b'=', 1)[1], aliases)
            if source.tname(row) not in GEOMETRIC_VALUES | STYLE_VALUES or lhs != rhs:
                raise ValueError(f'non-identical definition #{eid}')
            if shared.r(eid) >= 0:
                raise ValueError('removed ID still present')
        elif shared.r(eid) < 0 or shared.text(shared.r(eid)) != _rewritten(source, row, aliases, redirected):
            raise ValueError(f'retained entity #{eid} changed beyond reference substitution')
        else:
            expected_bytes.update(_rewritten(source, row, aliases, redirected))
    expected_bytes.update(source.mm[pos:])
    if hashlib.sha256(shared.mm).digest() != expected_bytes.digest():
        raise ValueError('non-entity bytes changed')
    return {'exact_removed_definition_checks': len(aliases),
            'retained_record_checks': shared.n, 'all_references_resolve': True,
            'topology_and_binding_ids_preserved': True}


def native_summary(path):
    """Read geometry/names only; presentation is proven separately at graph level."""
    from export_step_elements import shape_counts
    from cad_composition import native_bounds_m
    from validate_parts import (TDF_LabelSequence, XCAFDoc_DocumentTool, TDocStd_Document,
                                TCollection_ExtendedString, STEPCAFControl_Reader, IFSelect_RetDone)
    doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    reader = STEPCAFControl_Reader()
    for mode in ('Color', 'Layer', 'Props', 'Mat', 'GDT', 'SHUO', 'View', 'Meta', 'ProductMeta'):
        setter = getattr(reader, 'Set' + mode + 'Mode', None)
        if setter is not None:
            setter(False)
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.Transfer(doc):
        raise ValueError('native transfer failed')
    roots = TDF_LabelSequence(); tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    tool.GetFreeShapes(roots)
    solids, faces = shape_counts(doc)
    return {'roots': roots.Length(), 'solids': solids, 'faces': faces,
            'bounds_m': native_bounds_m(doc).tolist(),
            'transfer_scope': 'geometry and assembly names; presentation checked separately'}


def run(source_path, output, *, hierarchy=None, native_baseline=None):
    """Build a validated candidate in a new folder; never overwrite a source/export."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    start = time.perf_counter()
    try:
        load = Index if Path(source_path).suffix == '.npz' else Index.from_step
        with load(source_path) as ix:
            digest = hashlib.sha256(ix.mm).hexdigest()
            source = profile(ix)
            t = time.perf_counter(); aliases, evidence = plan_sharing(ix)
            plan_seconds = time.perf_counter() - t
            print(f'{len(aliases)} exact aliases planned in {plan_seconds:.2f}s', flush=True)
            t = time.perf_counter(); write_shared(ix, aliases, stage / 'field.step')
            write_seconds = time.perf_counter() - t
            t = time.perf_counter()
            with Index.from_step(stage / 'field.step', workers=1) as shared:
                parse_seconds = time.perf_counter() - t
                t = time.perf_counter(); proof = validate_shared(ix, shared, aliases)
                if hierarchy:
                    h = json.loads(Path(hierarchy).read_text())
                    proof['assembly_edges_checked'] = verify_assembly_graph(shared, h['assemblies'])
                validation_seconds = time.perf_counter() - t
                result = profile(shared)
                result['sha256'] = hashlib.sha256(shared.mm).hexdigest()
            if hashlib.sha256(ix.mm).hexdigest() != digest:
                raise ValueError('source changed during sharing')
            report = {'schema_version': 1, 'pass': 'share-exact-step-values-v1',
                      'source': {**source, 'path': str(Path(ix.source).resolve()), 'sha256': digest},
                      'output': result, 'evidence': evidence, 'proof': proof,
                      'alias_semantics': 'removed STEP definition ID to exact retained definition ID; topology/occurrence/style binding IDs remain distinct',
                      'aliases': {str(k): v for k, v in sorted(aliases.items())},
                      'timings_seconds': {'plan': plan_seconds, 'write': write_seconds,
                                          'output_serial_index': parse_seconds,
                                          'graph_validation': validation_seconds}}
        if hierarchy:
            # This remains explicitly the input's identity catalog. Consumers
            # resolve removed definition IDs through sharing.json, rather than
            # treating old private IDs/checksums as the optimized artifact's IDs.
            shutil.copyfile(hierarchy, stage / 'source-hierarchy.json')
            report['source_hierarchy'] = {
                'file': 'source-hierarchy.json',
                'sha256': hashlib.sha256((stage / 'source-hierarchy.json').read_bytes()).hexdigest(),
                'scope': 'unchanged input identity catalog; resolve removed IDs through aliases'}
        if native_baseline:
            t = time.perf_counter(); actual = native_summary(stage / 'field.step')
            baseline = json.loads(Path(native_baseline).read_text())
            if actual['roots'] != 1 or actual['solids'] != baseline['native_solids'] or actual['faces'] != baseline['native_faces'] or not np.allclose(actual['bounds_m'], baseline['bounds_m'], rtol=0, atol=1e-9):
                raise ValueError('native geometry coverage/bounds changed')
            report['native_validation'] = actual
            report['timings_seconds']['native_read'] = time.perf_counter() - t
        report['producer_sha256'] = {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('cad_share_values.py', 'p21index.py', 'cad_hierarchy.py', 'audit_step.py')}
        report['timings_seconds']['total'] = time.perf_counter() - start
        (stage / 'sharing.json').write_text(json.dumps(report, indent=2) + '\n')
        source_notice = Path(ix.source).resolve().parent / 'NOTICE.md'
        if not source_notice.is_file():
            source_notice = Path(__file__).resolve().parents[1] / 'NOTICE.md'
        (stage / 'NOTICE.md').write_text(source_notice.read_text() + '\n\n'
            '## Exact definition sharing candidate\n\n'
            'Only exact definition sharing is applied; layers, topology and placements remain.\n'
            'sharing.json records the input SHA-256 and removed-ID aliases.\n'
            'This candidate does not replace the reviewed stage-one release.\n')
        stage.rename(output)
        return report
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='STEP or optional parser index cache')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--hierarchy', type=Path, help='baseline hierarchy.json for assembly verification')
    parser.add_argument('--native-baseline', type=Path, help='baseline native-validation.json')
    args = parser.parse_args()
    report = run(args.source, args.out, hierarchy=args.hierarchy, native_baseline=args.native_baseline)
    print(json.dumps({k: v for k, v in report.items() if k not in {'source', 'output', 'aliases'}}, indent=2))
    print(f"STEP: {report['source']['bytes']} -> {report['output']['bytes']} bytes", flush=True)


if __name__ == '__main__':
    main()
