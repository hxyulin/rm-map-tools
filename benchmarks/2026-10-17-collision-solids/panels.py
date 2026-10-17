#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build source-owned thin-panel prisms and keep uncovered Dart contact geometry."""
import argparse
import json
from pathlib import Path
from audit import ROOT, native, module
import numpy as np
from cad_collision_profiles import native_loops, prism_mesh
from cad_local_lod import guarded_vertex_lod
from mesh_quality import deviation, distances, sample_points
from plan_cad_lods import digest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopoDS import TopoDS
from gltf_scene import read_glb, write_glb

save_mesh = module('equipment', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py').save_mesh
TARGETS = {'dart-station/frame': [1], 'dart-station/deck-and-shared-hardware': [122, 149, 178], 'dart-station/door-candidate': [4, 26, 27]}


def projected_overlap(a, b, normal):
    seed = np.eye(3)[np.argmin(abs(normal))]; x = np.cross(seed, normal); x /= np.linalg.norm(x); y = np.cross(normal, x); basis = np.array([x, y])
    boxes = []
    for row in [a, b]:
        lo, hi = np.array(row['bbox_mm']); corners = np.array([[xx, yy, zz] for xx in [lo[0], hi[0]] for yy in [lo[1], hi[1]] for zz in [lo[2], hi[2]]]) @ basis.T
        boxes.append([corners.min(0), corners.max(0)])
    a, b = np.array(boxes); intersection = np.maximum(0, np.minimum(a[1], b[1]) - np.maximum(a[0], b[0]))
    return float(np.prod(intersection) / max(1e-12, min(np.prod(a[1] - a[0]), np.prod(b[1] - b[0]))))


def pairs(records):
    planes = sorted([r for r in records if r['kind'] == 'Plane' and r['area_mm2'] >= 5000], key=lambda r: -r['area_mm2']); used = set(); result = []
    for a in planes:
        if a['native_face_index'] in used: continue
        candidates = []; n = np.array(a['normal'])
        for b in planes:
            if b['native_face_index'] == a['native_face_index'] or b['native_face_index'] in used: continue
            if n @ b['normal'] > -.999999: continue
            signed_depth = a['offset_mm'] + b['offset_mm']; depth = abs(signed_depth); ratio = min(a['area_mm2'], b['area_mm2']) / max(a['area_mm2'], b['area_mm2'])
            # STEP often splits one backing plane into many paint/relief faces.
            # An opposed fragment can establish thickness; it need not cover the
            # front's whole area. The complete generated slab is independently
            # checked against the approved contact surface below.
            if not .5 <= depth <= 8 or ratio < .05: continue
            overlap = projected_overlap(a, b, n)
            if overlap < .9: continue
            candidates.append((1 - ratio + abs(depth - 3) * .001, b, depth, overlap, 1 if signed_depth > 0 else -1))
        if not candidates: continue
        _, b, depth, overlap, sign = min(candidates, key=lambda v: v[0]); used.update([a['native_face_index'], b['native_face_index']]); result.append((a, b, depth, overlap, sign))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve()
    audit = json.loads((out / 'audit.json').read_bytes()); native_by = {r['id']: r for r in audit['components']}
    composition = json.loads((ROOT / 'out/rmuc2027-residual-equipment/composition.json').read_bytes()); visual_by = {r['id']: r for r in composition['components']}; rows = []
    for cid, selected in TARGETS.items():
        row = visual_by[cid]; visual = ROOT / row['candidate_glb']; baseline_path = ROOT / 'out/rmuc2027-game-lods' / cid / 'contact-6mm.npz'; baseline = np.load(baseline_path); approved = np.load(visual.with_suffix('.npz'))
        if digest(visual) != row['candidate_sha256']: raise ValueError('approved visual changed')
        source = ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'
        if digest(source) != native_by[cid]['source_step_sha256'] or digest(source) != row['source_step_sha256']: raise ValueError('native source changed')
        doc, reader, faces, shells, owners = native(source); bp, bt, bu = [baseline[k] for k in ['positions_mm', 'triangles', 'unit_ids']]; apoints, atris, au = [approved[k] for k in ['positions_mm', 'triangles', 'unit_ids']]
        chunks = []; triangles = []; members = []; proofs = []; offset = 0
        for unit in np.unique(bu):
            mask = bu == unit; used, inv = np.unique(bt[mask], return_inverse=True); q, f = bp[used], inv.reshape(-1, 3); previous = len(f)
            if unit in selected:
                old_mask = au == unit; ids, old = np.unique(atris[old_mask], return_inverse=True); p, t = apoints[ids], old.reshape(-1, 3); native_records = [r for r in native_by[cid]['faces'] if r['member'] == unit]; panels = []; accepted = []; rejected = []
                for a, b, depth, overlap, normal_sign in pairs(native_records):
                    try:
                        loops, profile = native_loops(faces.FindKey(a['native_face_index']), boundary_error_mm=.5, close_holes_below_mm=17)
                        pp, tt, topology = prism_mesh(loops, np.array(a['normal']) * normal_sign, depth)
                        values = distances(sample_points(pp, tt, count=len(tt)), p, t)
                        # Test all primitive vertices as well as every triangle's samples.
                        worst = float(max(values.max(), distances(pp, p, t).max()))
                        record = {'front_native_face': a['native_face_index'], 'back_native_face': b['native_face_index'], 'depth_mm': depth, 'normal_sign': normal_sign, 'projected_bounds_overlap': overlap, 'triangles': len(tt), 'maximum_panel_to_approved_surface_mm': worst, 'profile': profile, 'topology': topology}
                        if worst > 6: record['reason'] = 'new panel exceeds the six millimetre sampled surface allowance'; rejected.append(record); continue
                        panels.append((pp, tt)); accepted.append(record)
                    except ValueError as error: rejected.append({'front_native_face': a['native_face_index'], 'back_native_face': b['native_face_index'], 'reason': str(error)})
                if panels:
                    points = []; face_chunks = []; cursor = 0
                    for pp, tt in panels: points.append(pp); face_chunks.append(tt + cursor); cursor += len(pp)
                    pp, tt = np.concatenate(points), np.concatenate(face_chunks)
                    g = p[t]; samples = np.stack([g[:, 0], g[:, 1], g[:, 2], (g[:, 0] + g[:, 1]) / 2, (g[:, 1] + g[:, 2]) / 2, (g[:, 2] + g[:, 0]) / 2, g.mean(1)], axis=1)
                    error = distances(samples.reshape(-1, 3), pp, tt).reshape(-1, 7); covered = error.max(1) <= 2
                    qq, ff = np.concatenate([pp, p]), np.concatenate([tt, t[~covered] + len(pp)])
                    quality = deviation(p, t, qq, ff, count=max(len(t), len(ff)))
                    # A sparse guard previously forced some entire large
                    # members back to the input. Start again from the approved
                    # surface with every triangle sampled and lock any failing
                    # corner neighborhoods, rather than carrying that fallback.
                    locks = set(); lod_trials = []
                    for refinement in range(3):
                        dp, dt, _, lod = guarded_vertex_lod(p, t, np.zeros(len(t), dtype=np.int64), error_mm=3,
                            sampled_limit_mm=5, sample_count=max(96, min(262144, len(t))), maximum_iterations=16,
                            protected_vertex_indices=np.array(sorted(locks), dtype=np.int64))
                        vertex_errors = distances(p, dp, dt); bad = np.flatnonzero(vertex_errors > 5)
                        lod_trials.append({'triangles': len(dt), 'maximum_source_vertex_error_mm': float(vertex_errors.max()), 'locked_vertices': len(locks)})
                        if not len(bad): break
                        locks.update(map(int, t[np.isin(t, bad).any(axis=1)].ravel()))
                    dense_g = dp[dt]
                    dense_samples = np.stack([dense_g[:, 0], dense_g[:, 1], dense_g[:, 2], (dense_g[:, 0] + dense_g[:, 1]) / 2, (dense_g[:, 1] + dense_g[:, 2]) / 2, (dense_g[:, 2] + dense_g[:, 0]) / 2, dense_g.mean(1)], axis=1)
                    dense_covered = distances(dense_samples.reshape(-1, 3), pp, tt).reshape(-1, 7).max(1) <= 1
                    dq, df = np.concatenate([pp, dp]), np.concatenate([tt, dt[~dense_covered] + len(pp)])
                    dense_quality = deviation(p, t, dq, df, count=max(len(t), len(df)))
                    dense_quality['maximum_vertex_distance_mm'] = float(max(distances(p, dq, df).max(), distances(dq, p, t).max()))
                    dense_accepted = len(df) < min(len(ff), previous) and max(dense_quality['max'], dense_quality['maximum_vertex_distance_mm']) <= 6
                    if dense_accepted: qq, ff, quality = dq, df, dense_quality
                    accepted_unit = len(ff) < previous and quality['max'] <= 6
                    proof = {'source_member': int(unit), 'reference_visual_triangles': len(t), 'previous_collision_triangles': previous, 'candidate_triangles': len(ff), 'retained_contact_triangles': len(ff) - len(tt), 'coverage_sample_allowance_mm': 1 if dense_accepted else 2, 'dense_remainder': {'accepted': dense_accepted, 'trials': lod_trials, 'sampled_deviation_mm': dense_quality}, 'sampled_approved_deviation_mm': quality, 'accepted': accepted_unit, 'panels': accepted, 'rejected_panels': rejected}
                    if accepted_unit: q, f = qq, ff
                else: proof = {'source_member': int(unit), 'accepted': False, 'reason': 'no qualified panel pair', 'rejected_panels': rejected}
                proofs.append(proof); print(cid, int(unit), previous, '->', len(f), 'panels', len(panels), 'accepted', proof['accepted'], flush=True)
            chunks.append(q); triangles.append(f + offset); offset += len(q); members.extend([unit] * len(f))
        q, f = np.concatenate(chunks), np.concatenate(triangles); quality = deviation(apoints, atris, q, f, count=32768)
        if quality['max'] > 6: raise ValueError('complete definition sampled surface guard failed ' + cid + ' ' + str(quality))
        folder = out / cid; folder.mkdir(parents=True, exist_ok=True); save_mesh(folder, 'panels', q, f, np.zeros(len(f), dtype=np.int64), ['0.45,0.65,0.80'], np.array(members))
        path = folder / 'panels.glb'; d, blob = read_glb(path)
        for node in d['nodes']:
            if 'mesh' in node: node['extras'].update(collision_only=True, derived_geometry=True, native_identity_claim=False, source_native_shell_index=node['extras'].pop('native_shell_index'))
        write_glb(path, d, blob)
        result = {'id': cid, 'uses': row['uses'], 'visual_triangles': len(atris), 'previous_collision_triangles': len(bt), 'collision_triangles': len(f), 'source_step_sha256': digest(source), 'approved_glb_sha256': digest(visual), 'approved_npz_sha256': digest(visual.with_suffix('.npz')), 'previous_collision_npz_sha256': digest(baseline_path), 'sampled_approved_deviation_mm': quality, 'members': proofs, 'outputs_sha256': {name: digest(folder / name) for name in ['panels.npz', 'panels.glb']}}
        rows.append(result); print('COMPLETE', cid, len(bt), '->', len(f), quality, flush=True)
    (out / 'panels-summary.json').write_text(json.dumps({'components': rows, 'audit_sha256': digest(out / 'audit.json'), 'producer_sha256': digest(__file__), 'pass_sha256': digest(ROOT / 'python/cad_collision_profiles.py'), 'scope': 'Collision-only source-paired finite panel prisms plus uncovered approved surfaces. Each native rigid member stays separate; intersections between its own closed panel slabs are intentional. Six millimetre sampled surface guard, no installed geometry or rule detector change.'}, indent=2) + '\n')


if __name__ == '__main__': main()
