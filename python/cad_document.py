# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-owned, in-memory CAD context for discovery, working passes and exporters.

Keep the exact STEP entity graph, typed assembly/ownership views and a lazily
imported native XCAF working model together. Geometry, source identity,
appearance and instances are separate concerns. No intermediate storage format
or mesh is required. Source bytes remain authoritative across OCCT healing.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
from p21index import Index
from p21model import Model, STR_RE, decode_p21


@dataclass(frozen=True)
class SourceEntity:
    """A lazy source entity reference, qualified by its owning document's SHA-256."""
    document: 'CadDocument'
    id: int

    @property
    def row(self):
        self.document.require_open()
        row = self.document.index.r(self.id)
        if row < 0:
            raise ValueError(f'unresolved source entity #{self.id}')
        return row

    @property
    def kind(self):
        return self.document.index.tname(self.row)

    @property
    def raw(self):
        """Original Part 21 bytes, including numeric spelling and source strings."""
        return self.document.index.text(self.row)

    @property
    def reference_ids(self):
        """A read-only view of reference IDs; large layer lists are not copied."""
        view = self.document.index.refs_of(self.row).view()
        view.flags.writeable = False
        return view

    @property
    def strings(self):
        return tuple(decode_p21(s) for s in STR_RE.findall(self.raw))


@dataclass(frozen=True)
class WorkingModel:
    """Native mutable XCAF model plus its STEP transfer reader; source graph stays separate.

    The reader is retained for transfer diagnostics and future explicit bindings.
    OCCT face ordinals are not STEP face IDs. Passes mutate this derived model,
    never the read-only source graph or the source STEP file.
    """
    document: object
    reader: object
    available_metadata_modes: dict
    source_sha256: str


class CadDocument:
    """Own exact source data and reusable typed views for the duration of a pipeline."""

    def __init__(self, index, model=None, *, owns_index=True, expected_sha256=None):
        self.index = index
        self._owns_index = owns_index
        self._closed = False
        self.source_path = Path(index.source).resolve()
        self.source_sha256 = hashlib.sha256(index.mm).hexdigest()
        if expected_sha256 is not None and self.source_sha256 != expected_sha256:
            if owns_index:
                index.close()
            raise ValueError('source SHA-256 mismatch')
        try:
            self.model = Model(index) if model is None else model
        except Exception:
            if owns_index:
                index.close()
            raise
        self._transforms = None
        self._working = None

    @classmethod
    def from_step(cls, path, *, workers=None, expected_sha256=None, intern_layers=False):
        """Load STEP in memory, optionally pooling exact ordered layer memberships."""
        return cls(Index.from_step(path, workers=workers, intern_layers=intern_layers), expected_sha256=expected_sha256)

    @classmethod
    def from_index(cls, path, *, expected_sha256=None):
        """Reuse an optional parser cache with the same source-owned document API."""
        return cls(Index(path), expected_sha256=expected_sha256)

    def require_open(self):
        if self._closed:
            raise ValueError('CAD document is closed')

    def entity(self, step_id):
        ref = SourceEntity(self, int(step_id))
        ref.row  # Validate the reference now, not after a pass has used it.
        return ref

    def entities(self, *kinds):
        """Lazily access any original entity family, including unmodeled metadata."""
        self.require_open()
        for row in self.index.rows_of(*kinds):
            yield SourceEntity(self, int(self.index.ids[row]))

    def styles(self, target_id):
        """Original style records targeting an entity; no front/back or RGB reduction."""
        target = self.entity(target_id)
        return tuple(SourceEntity(self, int(self.index.ids[row]))
                     for row in self.model.style_of_target.get(target.row, []))

    @property
    def geometry_length_units(self):
        """Original geometry-context units; exclude unrelated density unit declarations."""
        self.require_open()
        from audit_step import geometry_length_units
        return geometry_length_units(self.index)

    @property
    def transforms(self):
        """Explicit source child-to-parent matrices, in source geometry length units."""
        self.require_open()
        if self._transforms is None:
            from mesh_parts import nauo_transforms
            self._transforms = nauo_transforms(self.index, self.model)
        return self._transforms

    def subtree(self, root):
        """Yield product row, world matrix and relative occurrence rows in source order.

        Root is a source product row. Coincident instances stay separate. Missing
        placements, unresolved children and cycles fail instead of inventing data.
        """
        def walk(product, matrix, path, ancestors):
            if product in ancestors:
                raise ValueError('cyclic source assembly')
            yield product, matrix, path
            for occurrence, child in self.model.children.get(product, []):
                if child is None or occurrence not in self.transforms:
                    raise ValueError('source occurrence lacks child or explicit placement')
                local = self.transforms[occurrence]
                if (local.shape != (4, 4) or not np.isfinite(local).all()
                        or not np.allclose(local[3], [0, 0, 0, 1])):
                    raise ValueError('invalid source placement')
                yield from walk(child, matrix @ local, path+(occurrence,), ancestors | {product})
        self.require_open()
        yield from walk(root, np.eye(4), (), set())

    def working_model(self):
        """Import one mutable native XCAF working model directly from original STEP.

        Source-only discovery never calls this. OCCT may heal on import; the
        exact source graph is retained and no face-ID correspondence is assumed.
        """
        self.require_open()
        if self._working is None:
            self.verify_source()
            from validate_parts import read_part
            doc, reader, error = read_part(str(self.source_path))
            if error:
                raise ValueError(f'CAD import failed: {error}')
            modes = {name: hasattr(reader, 'Set'+name+'Mode') for name in
                     ('Color', 'Name', 'Layer', 'Props', 'Mat', 'GDT', 'SHUO', 'View', 'Meta', 'ProductMeta')}
            self._working = WorkingModel(doc, reader, modes, self.source_sha256)
            self.verify_source()
        return self._working

    def node_identity(self, product, path=()):
        """Small exporter provenance, independent of shared geometry or display names."""
        self.require_open()
        ids = self.index.ids
        bodies = [int(ids[b]) for b, rep in self.model.bodies if self.model.rep_product.get(rep) == product]
        return {'schema_version': 1, 'source_sha256': self.source_sha256,
                'product_id': int(ids[product]), 'body_ids': bodies,
                'relative_occurrence_path': [int(ids[r]) for r in path],
                'mesh_to_source_face_mapping': 'unavailable: OCCT import may heal or split faces'}

    def verify_source(self):
        self.require_open()
        with self.source_path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != self.source_sha256:
                raise ValueError('source STEP changed while document was open')

    def close(self):
        if not self._closed:
            self._working = None
            if self._owns_index:
                self.index.close()
            self._closed = True

    def __enter__(self):
        self.require_open()
        return self

    def __exit__(self, *_):
        self.close()
