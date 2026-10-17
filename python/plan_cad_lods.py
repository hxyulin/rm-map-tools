#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Expand a reviewed stage-one hierarchy into a compact, source-pinned LOD plan.

Standard library only. No meshing, deletion, fitting or runtime changes occur.
Output keeps definition policies pooled independently of occurrence bindings.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from cad_lod_policy import Node, Quality, plan


IDENTITY = [[float(i == j) for j in range(4)] for i in range(4)]
DEFAULTS = {('visual', 'near'): Quality(.1, mesh_mm=.09),
            ('visual', 'medium'): Quality(1, mesh_mm=.9),
            ('visual', 'far'): Quality(4, mesh_mm=3.6),
            ('collision', 'fixed'): Quality(.1, mesh_mm=.09)}


def digest(path):
    """Hash a large source without loading it into memory."""
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def matrix(value):
    """Validate an invertible affine source placement, including reflections."""
    if not isinstance(value, list) or len(value) != 4 or any(not isinstance(r, list) or len(r) != 4 for r in value):
        raise ValueError('expected a 4x4 placement matrix')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for r in value for v in r):
        raise ValueError('nonfinite placement')
    if value[3] != [0, 0, 0, 1]:
        raise ValueError('placement must be affine')
    a, b, c = [row[:3] for row in value[:3]]
    det = a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    if not math.isfinite(det) or det == 0:
        raise ValueError('singular placement')
    return value


def multiply(a, b):
    """Compose source world and child affine transforms without re-encoding CAD."""
    return matrix([[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)])


def scale_bound(value):
    """Conservative spectral-norm bound from the absolute row sums of AᵀA."""
    bound = max(sum(abs(sum(value[k][i]*value[k][j] for k in range(3))) for j in range(3)) for i in range(3))
    return math.sqrt(bound) * (1 + 1e-14)  # Floating-point accumulation margin.


def quality_map(settings):
    """Decode explicit channel/level JSON settings; reject unknown quality fields."""
    result = {}
    for channel, levels in settings.items():
        if channel not in ('visual', 'collision') or not isinstance(levels, dict):
            raise ValueError('unknown channel or invalid level map')
        for level, values in levels.items():
            if not isinstance(level, str) or not level or not isinstance(values, dict):
                raise ValueError('invalid level settings')
            try:
                result[channel, level] = Quality(**values)
            except TypeError as error:
                raise ValueError('unknown or missing quality field') from error
    return result


def build_plan(catalog, *, overrides=None, roles=None):
    """Retain all definitions and placed uses, resolving reviewed part overrides.

    Overrides map exact component IDs to quality maps. Expanded occurrence IDs
    are product paths with child slots, so repeated identical children remain
    separate. All nodes stay protected pending separate semantic/feature review.
    """
    if catalog.get('schema_version') != 1 or catalog.get('source_geometry_preserved') is not True:
        raise ValueError('expected source-preserving stage-one hierarchy v1')
    if catalog.get('assembly_graph_verified') is not True or catalog.get('source_world_placements_verified') is not True:
        raise ValueError('stage-one assembly/placement evidence required')
    components = catalog['components']
    definitions = {c['export_product_id']: c for c in components}
    assemblies = {a['product_id']: a for a in catalog['assemblies']}
    if len(definitions) != len(components) or len(assemblies) != len(catalog['assemblies']) or set(definitions) & set(assemblies):
        raise ValueError('duplicate hierarchy product identity')
    component_ids = {c['id'] for c in components}
    if len(component_ids) != len(components):
        raise ValueError('duplicate component ID')
    faces = set()
    for component in components:
        selected = set(component['face_ids'])
        if len(selected) != component['face_count'] or len(selected) != len(component['face_ids']) or selected & faces:
            raise ValueError('component faces overlap or counts disagree')
        faces.update(selected)
    if len(faces) != catalog['source_face_definitions']:
        raise ValueError('source face coverage incomplete')
    overrides = overrides or {}
    if set(overrides) - component_ids:
        raise ValueError('unknown component override')
    nodes = []
    uses = []
    per_node = {}
    visited = set()
    placed_faces = 0

    def visit(product, parent, node_id, world, active):
        nonlocal placed_faces
        if product in active:
            raise ValueError('assembly cycle')
        if product not in definitions and product not in assemblies:
            raise ValueError('unresolved child product')
        visited.add(product)
        component = definitions.get(product)
        nodes.append(Node(node_id, parent, component['id'] if component else None,
                          scale_bound(world), protected=True))
        uses.append({'id': node_id, 'parent': parent, 'product_id': product,
                     'name': component['id'] if component else assemblies[product]['name'],
                     'world_matrix_mm': world,
                     'component_id': component['id'] if component else None})
        if component:
            placed_faces += component['face_count']
            if component['id'] in overrides:
                per_node[node_id] = quality_map(overrides[component['id']])
        else:
            for slot, child in enumerate(assemblies[product]['children']):
                visit(child['product_id'], node_id, f"{node_id}/{slot}-p{child['product_id']}",
                      multiply(world, matrix(child['matrix_mm'])), active | {product})

    root = catalog['root_product_id']
    visit(root, None, f'p{root}', IDENTITY, set())
    if visited != set(definitions) | set(assemblies):
        raise ValueError('unreachable hierarchy definitions')
    if placed_faces != catalog['expected_placed_faces']:
        raise ValueError('placed face accounting mismatch')
    requests = plan(nodes, DEFAULTS, per_node)
    if roles is not None:
        if roles.source_sha256 != catalog['files_sha256']['field.step']:
            raise ValueError('LOD marking roles/source mismatch')
        requests = tuple(r for r in requests if r.channel != 'collision' or roles.collision_enabled(r.prototype))
    profiles = {}
    bindings = []
    for request in requests:
        # This pools identical requests only, not unverified geometric matches.
        profile = {'component_id': request.prototype, 'channel': request.channel,
                   'quality_local_mm': asdict(request.quality), 'protected': request.protected}
        encoded = json.dumps(profile, sort_keys=True, separators=(',', ':'))
        key = hashlib.sha256(encoded.encode()).hexdigest()
        profiles.setdefault(key, profile)
        bindings.append({'node_id': request.node, 'level': request.level, 'profile': key})
    counts = Counter(u['component_id'] for u in uses if u['component_id'])
    return {
        'schema_version': 1, 'effect': 'planning-only',
        'defaults_world_mm': {f'{c}/{l}': asdict(q) for (c, l), q in DEFAULTS.items()},
        'summary': {'component_definitions': len(components), 'placed_component_uses': sum(counts.values()),
                    'expanded_hierarchy_nodes': len(nodes), 'unique_source_faces': len(faces),
                    'placed_source_faces': placed_faces, 'lod_request_bindings': len(bindings),
                    'pooled_request_profiles': len(profiles)},
        'definitions': [{'id': c['id'], 'export_product_id': c['export_product_id'],
                         'source_product_id': c['source_product_id'], 'source_faces': c['face_count'],
                         'placed_uses': counts[c['id']], 'review_status': c['review_status'],
                         'collision_enabled': roles.collision_enabled(c['id']) if roles else True}
                        for c in components],
        'nodes': uses, 'request_profiles': profiles, 'bindings': bindings,
        'unresolved': ['Semantic roles, scoring/light protection details and motion owners are not bound.',
                       'Cross-component interface sample networks are not bound.',
                       'No achieved deviation, triangle counts or payload savings measured by this plan.'],
        'policy': 'All geometry retained and protected; fit/quantization/removal/merging disabled. '
                  'Source-preserving tessellation requests need validation before export.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hierarchy', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--overrides', type=Path, help='Exact component-ID to channel/level Quality JSON')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--roles', type=Path, help='Source-owned visual-only marking policy')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    before = digest(args.hierarchy)
    catalog = json.loads(args.hierarchy.read_text())
    source_sha = digest(args.source)
    if catalog['files_sha256']['field.step'] != source_sha:
        raise ValueError('hierarchy/source checksum mismatch')
    settings = json.loads(args.overrides.read_text()) if args.overrides else {}
    roles = None
    if args.roles:
        from cad_collision_roles import CollisionRoles
        roles = CollisionRoles.read(args.roles, args.hierarchy)
    report = build_plan(catalog, overrides=settings, roles=roles)
    if args.roles:
        report['roles_sha256'] = digest(args.roles)
        report['policy'] += ' Whole visual-only marking components have no collision LOD request; embedded markings retain unpainted backing.'
    if digest(args.hierarchy) != before or digest(args.source) != source_sha:
        raise ValueError('inputs changed while planning')
    report['input_sha256'] = {'hierarchy': before, 'source': source_sha}
    report['overrides'] = settings
    report['producer_sha256'] = {name: digest(Path(__file__).with_name(name))
                                 for name in ('plan_cad_lods.py', 'cad_lod_policy.py', 'cad_collision_roles.py')}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
