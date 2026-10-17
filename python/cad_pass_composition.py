# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose explicitly owned shell edits without simplifying earlier approximations.

Native shell IDs must already be bound to one checksum-scoped work part. A
changed shell is reduced from the edited source mesh; other shells are copied
from the approved reference. Derived negative IDs are never rebound to CAD.
"""
import numpy as np


def subset(mesh, selection):
    """Extract triangles without rounding their positions or material bindings."""
    t = mesh['triangles'][selection]
    used, inverse = np.unique(t, return_inverse=True)
    return (mesh['positions_mm'][used], inverse.reshape(-1, 3),
            mesh['material_ids'][selection])


def compose_shells(reference, edited, changed_units, reduce_shell, *, omit_units=()):
    """Replay selected edits, retain untouched shells exactly and omit owned voids.

    ``reduce_shell(unit, p, t, m)`` returns a mesh and a validation record. Its
    error reference is the edited source, never the previous approximation.
    Omitted units take precedence; a fully deleted changed unit stays absent.
    Material IDs use the reference palette after explicit caller-side remapping.
    """
    changed = set(map(int, changed_units)); omitted = set(map(int, omit_units))
    known = set(map(int, reference['unit_ids']))
    if changed - known or omitted - known:
        raise ValueError('edit refers to an unknown source shell')
    if set(map(int, edited['unit_ids'])) - known:
        raise ValueError('edited mesh invents source shell identities')
    positions, triangles, materials, units, records = [], [], [], [], []
    offset = 0
    for unit in sorted(known):
        if unit in omitted:
            records.append({'unit': unit, 'operation': 'qualified-cavity-omission'})
            continue
        before = int(np.count_nonzero(reference['unit_ids'] == unit))
        if unit in changed:
            selection = edited['unit_ids'] == unit
            if not selection.any():
                records.append({'unit': unit, 'operation': 'selected-hardware-omission', 'before': before, 'after': 0})
                continue
            p, t, m = subset(edited, selection)
            p, t, m, proof = reduce_shell(unit, p, t, m)
            operation = 'edited-source-replay'
        else:
            p, t, m = subset(reference, reference['unit_ids'] == unit)
            proof = {'exact_reference_positions_materials': True}
            operation = 'retain-approved-shell'
        positions.append(p); triangles.append(t + offset); materials.append(m)
        units.append(np.full(len(t), unit, dtype=np.int64)); offset += len(p)
        records.append({'unit': unit, 'operation': operation, 'before': before,
                        'after': len(t), 'validation': proof})
    if not triangles:
        return (np.empty((0, 3)), np.empty((0, 3), dtype=np.int64),
                np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64), records)
    return tuple(np.concatenate(v) for v in (positions, triangles, materials, units)) + (records,)
