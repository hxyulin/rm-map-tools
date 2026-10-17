# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-owned visual-only terrain markings and coverage-preserving collision.

Whole marking solids contribute no collision. Markings embedded in structural
faces are visual-only uses; a separate unpainted backing retains their footprint
until a backing-domain coalescing pass reduces that geometry. No holes are made
by dropping painted caps without replacements.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


class CollisionRoles:
    """Validated marking bindings against one immutable source/hierarchy pair."""
    def __init__(self, data, hierarchy, *, hierarchy_sha256):
        if data.get('schema_version') != 1:
            raise ValueError('unsupported collision role schema')
        if data.get('source_sha256') != hierarchy['files_sha256']['field.step']:
            raise ValueError('collision roles/source mismatch')
        if data.get('hierarchy_sha256') != hierarchy_sha256:
            raise ValueError('collision roles/hierarchy mismatch')
        components = {c['id']: set(c['face_ids']) for c in hierarchy['components']}
        self._entries = {}
        for entry in data['entries']:
            cid = entry['component_id']
            if cid not in components or cid in self._entries:
                raise ValueError('unknown or duplicate marking component')
            if entry.get('role') != 'marking' or entry.get('visual') is not True or entry.get('collision') is not False:
                raise ValueError('markings must be visual-only')
            selected = entry['source_face_ids']
            if (not selected or any(type(f) is not int for f in selected) or
                    len(set(selected)) != len(selected) or not set(selected) <= components[cid]):
                raise ValueError('invalid marking source face ownership')
            selection = entry.get('selection')
            if selection not in ('component', 'faces'):
                raise ValueError('unknown marking selection')
            if selection == 'component' and set(selected) != components[cid]:
                raise ValueError('whole marking must own complete component')
            if entry.get('backing_required') is not (selection == 'faces'):
                raise ValueError('embedded marking needs unpainted collision backing')
            self._entries[cid] = copy.deepcopy(entry)
        self.source_sha256 = data['source_sha256']
        self._components = components

    @classmethod
    def read(cls, path, hierarchy):
        """Read roles and byte-pinned hierarchy; reject mismatched source revisions."""
        raw = Path(hierarchy).read_bytes()
        return cls(json.loads(Path(path).read_bytes()), json.loads(raw),
                   hierarchy_sha256=hashlib.sha256(raw).hexdigest())

    def binding(self, component_id):
        """Return a caller-owned role record, or None for unclassified geometry."""
        if component_id not in self._components:
            raise ValueError('unknown source component')
        return copy.deepcopy(self._entries.get(component_id))

    def collision_enabled(self, component_id):
        """Whether this component needs structural or unpainted backing collision."""
        entry = self.binding(component_id)
        return entry is None or entry['selection'] != 'component'

    def partition(self, component_id, source_face_ids):
        """Partition triangle indices into structure, marking and generated backing.

        Every embedded marking triangle is copied to neutral backing coverage;
        its painted use contributes no collision. Consumers must include both
        structural and backing lists until a validated domain rebuild replaces
        the backing. These lists are not a claim of triangle savings for inlays.
        """
        entry = self.binding(component_id)
        ids = list(map(int, source_face_ids))
        if not set(ids) <= self._components[component_id]:
            raise ValueError('triangle source face is outside component')
        selected = set(entry['source_face_ids']) if entry else set()
        marking = [i for i, face in enumerate(ids) if face in selected]
        structural = [i for i, face in enumerate(ids) if face not in selected]
        backing = marking.copy() if entry and entry['backing_required'] else []
        return {'structural': structural, 'visual_only_marking': marking,
                'unpainted_backing': backing, 'collision': sorted(structural + backing)}
