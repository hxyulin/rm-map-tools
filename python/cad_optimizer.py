# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-backed optimizer IR: shared recipes, independent identity and placement.

This is an in-memory representation, not a STEP emitter or a mesh optimizer.
A shared topology recipe is not a welded topological entity: source bindings
retain the original child IDs and incidence. Keep the CadDocument open. The
source document also retains unsupported metadata, names and style overrides.
"""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import json
import math
from pathlib import Path
import re

import numpy as np
from audit_geometry_duplicates import GeometryFingerprints
from cad_passes import CadScene
from p21index import TOK

# Display labels only, not arbitrary strings in unknown entity families.
DISPLAY_NAMED = set('CARTESIAN_POINT DIRECTION VECTOR AXIS1_PLACEMENT AXIS2_PLACEMENT_2D AXIS2_PLACEMENT_3D LINE CIRCLE ELLIPSE PLANE CYLINDRICAL_SURFACE CONICAL_SURFACE SPHERICAL_SURFACE TOROIDAL_SURFACE B_SPLINE_CURVE_WITH_KNOTS B_SPLINE_SURFACE_WITH_KNOTS SURFACE_OF_LINEAR_EXTRUSION SURFACE_OF_REVOLUTION VERTEX_POINT EDGE_CURVE ORIENTED_EDGE EDGE_LOOP FACE_BOUND FACE_OUTER_BOUND ADVANCED_FACE OPEN_SHELL CLOSED_SHELL ORIENTED_CLOSED_SHELL SHELL_BASED_SURFACE_MODEL MANIFOLD_SOLID_BREP BREP_WITH_VOIDS FACETED_BREP'.split())
NAME = re.compile(rb"^([A-Z_0-9]+\s*\(\s*)'(?:[^']|'')*'")
NUMBER = rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?'
TOKEN = re.compile(rb"'(?:[^']|'')*'|\"[^\"]*\"|/\*.*?\*/|#(\d+)|(?<![A-Za-z0-9_])(" + NUMBER + rb')|\s+', re.S)
PARAMETER_COUNTS = {'LINE': 0, 'PLANE': 0, 'CIRCLE': 1, 'ELLIPSE': 2,
                    'CYLINDRICAL_SURFACE': 1, 'CONICAL_SURFACE': 2,
                    'SPHERICAL_SURFACE': 1, 'TOROIDAL_SURFACE': 2}


def decimal_key(literal):
    """Canonical exact decimal value without binary floats or precision rounding.

    INTEGER and REAL spellings remain distinct, as do positive/negative real
    zero. Labels and enums never pass through this function. Exponents are
    represented symbolically; large values are not expanded into zero strings.
    """
    if re.fullmatch(NUMBER, literal) is None:
        raise ValueError('not a numeric literal')
    if b'.' not in literal and b'e' not in literal.lower():
        return b'~I' + str(int(literal)).encode()
    value = Decimal(literal.decode('ascii'))
    sign, digits, exponent = value.as_tuple()
    if not value.is_finite():
        raise ValueError('non-finite parameter')
    digits = list(digits)
    if not any(digits):
        digits, exponent = [0], 0
    else:
        while digits[-1] == 0:
            digits.pop(); exponent += 1
    return b'~R' + (b'-' if sign else b'') + bytes(48+d for d in digits) + b'E' + str(exponent).encode()


def direction_record(text):
    """Canonical positive-scale direction ratios using integer arithmetic only."""
    match = re.fullmatch(rb"DIRECTION\s*\(\s*''\s*,\s*\(([^()]*)\)\s*\)\s*;", text)
    if match is None:
        return None  # Unknown syntax is retained by the ordinary recipe path.
    parts = [value.strip() for value in match.group(1).split(b',')]
    if len(parts) not in (2, 3) or any(re.fullmatch(NUMBER, v) is None for v in parts):
        return None
    values = [Decimal(value.decode()).as_tuple() for value in parts]
    exponent = min(value.exponent for value in values)
    if max(value.exponent for value in values) - exponent > 256:
        return None  # Avoid exploding pathological exponents into huge integers.
    integers = [(-1 if v.sign else 1) * int(''.join(map(str, v.digits))) * 10 ** (v.exponent-exponent) for v in values]
    divisor = math.gcd(*integers)
    if divisor == 0:
        raise ValueError('zero direction ratios')
    # gcd is positive: an opposite direction must remain a different recipe.
    return b"DIRECTION('',(" + b','.join(b'~Q'+str(v//divisor).encode() for v in integers) + b'));'


def canonical_record(index, row, resolve, *, decimals, display_names, directions=False):
    """Build a recipe key; reference and string tokens remain unambiguous."""
    text = index.text(row).split(b'=', 1)[1].strip()
    if display_names and index.tname(row) in DISPLAY_NAMED:
        text = NAME.sub(rb"\1''", text, count=1)
    if directions and display_names and index.tname(row) == 'DIRECTION':
        normalized = direction_record(text)
        if normalized is not None:
            return normalized
    def replace(match):
        if match.group(1) is not None:
            return b'#' + str(resolve(int(match.group(1)))).encode()
        if match.group(2) is not None:
            return decimal_key(match.group(2)) if decimals else match.group(2)
        value = match.group()
        return value if value.startswith((b"'", b'"')) else b''
    return TOKEN.sub(replace, text)


def unit_profile(document):
    """Require one exact geometry-context unit profile before global sharing.

    All assigned units are included, especially source angle units; a cone's
    degree-valued angle must never be silently treated as radians.
    """
    ix = document.index; hashes = GeometryFingerprints(ix, ignore_display_names=False)
    profiles = set(); contexts = []
    for row in ix.rows_of('CPLX'):
        text = ix.text(int(row))
        # Removing literals/comments prevents their contents masquerading as units.
        text = TOK.sub(lambda m: b'' if m.group().startswith((b"'", b'/*')) else m.group(), text)
        match = re.search(rb'GLOBAL_UNIT_ASSIGNED_CONTEXT\s*\(\s*\(([^)]*)\)\s*\)', text)
        if match:
            units = [int(v) for v in re.findall(rb'#(\d+)', match.group(1))]
            if not units:
                raise ValueError('empty geometry unit profile')
            profiles.add(tuple(sorted(hashes.signature(ix.r(v)).hex() for v in units)))
            contexts.append(int(ix.ids[row]))
    if len(profiles) != 1:
        raise ValueError('optimizer requires one explicit geometry unit profile')
    return {'unit_graph_sha256': list(next(iter(profiles))), 'context_source_ids': contexts,
            'policy': 'source units retained; no conversion to metres/radians'}


def readonly(values, dtype=None):
    values = np.array(values, dtype=dtype, copy=True)
    values.flags.writeable = False
    return values


@dataclass(frozen=True)
class RecipePool:
    """Packed canonical records and row bindings; not independent topology IDs."""
    document: object
    records: bytes
    offsets: object
    kinds: object
    source_to_recipe: object
    normalize_decimals: bool
    remove_display_names: bool
    normalize_directions: bool

    def record(self, recipe):
        """Return an internal recipe token stream, which is deliberately not STEP."""
        return self.records[int(self.offsets[recipe]):int(self.offsets[recipe+1])]

    def recipe_for_source(self, entity_id):
        self.document.require_open()
        row = self.document.index.r(entity_id)
        if row < 0 or self.source_to_recipe[row] < 0:
            raise ValueError('source entity is outside this recipe pool')
        return int(self.source_to_recipe[row])

    def source_children(self, entity_id):
        """Keep original incidence, identity and repeated refs independently of recipes."""
        self.recipe_for_source(entity_id)
        return self.document.entity(entity_id).reference_ids

    def statistics(self):
        ix = self.document.index
        rows = np.flatnonzero(self.source_to_recipe >= 0)
        source = np.bincount(ix.types[rows], minlength=len(ix.typenames))
        shared = np.bincount(self.kinds, minlength=len(ix.typenames))
        return {'source_records': len(rows), 'recipe_definitions': len(self.kinds),
                'packed_record_bytes': len(self.records),
                'offset_and_kind_bytes': self.offsets.nbytes + self.kinds.nbytes,
                'source_binding_array_bytes': self.source_to_recipe.nbytes,
                'source_record_text_bytes': int(ix.lens[rows].sum()),
                'by_type': {name: {'source': int(source[i]), 'recipes': int(shared[i])}
                            for i, name in enumerate(ix.typenames) if source[i]}}

    def validate(self):
        """Recheck every recipe against its source and every source-child binding."""
        ix = self.document.index
        rows = np.flatnonzero(self.source_to_recipe >= 0)
        for row in rows:
            row = int(row)
            expected = canonical_record(ix, row, self.recipe_for_source,
                                        decimals=self.normalize_decimals,
                                        display_names=self.remove_display_names,
                                        directions=self.normalize_directions)
            if expected != self.record(int(self.source_to_recipe[row])):
                raise ValueError(f'recipe changed at source #{int(ix.ids[row])}')
        return len(rows)


def build_pool(document, roots, *, decimals, display_names, directions=False):
    """Intern complete ordered construction graphs, with cycle/missing-ref rejection."""
    ix = document.index
    bindings = np.full(ix.n, -1, dtype=np.int32); active = set()
    definitions = {}; records = []; offsets = [0]; kinds = []
    def intern(entity_id):
        row = ix.r(entity_id)
        if row < 0:
            raise ValueError('unresolved recipe reference')
        if bindings[row] >= 0:
            return int(bindings[row])
        if row in active:
            raise ValueError('cyclic recipe graph')
        active.add(row)
        key = canonical_record(ix, row, intern, decimals=decimals, display_names=display_names, directions=directions)
        recipe = definitions.get(key)
        if recipe is None:
            recipe = len(records); definitions[key] = recipe
            records.append(key); offsets.append(offsets[-1] + len(key)); kinds.append(int(ix.types[row]))
        bindings[row] = recipe; active.remove(row)
        return recipe
    for row in roots:
        intern(int(ix.ids[row]))
    return RecipePool(document, b''.join(records), readonly(offsets, np.uint64),
                      readonly(kinds, np.uint16), readonly(bindings), decimals, display_names, directions)


@dataclass(frozen=True)
class AnalyticPrototype:
    """Frame-free analytic construction; parameters retain exact source units."""
    kind: str
    dimension: int
    parameters: tuple


@dataclass(frozen=True)
class AnalyticUse:
    """One source primitive with its original frame/parameterization references."""
    source_id: int
    prototype: int
    frame_source_ids: tuple


@dataclass(frozen=True)
class AnalyticCatalog:
    """Analytic shapes share intrinsic recipes; trims and topology stay source uses."""
    document: object
    prototypes: tuple
    uses: object  # sorted (source id, prototype id, frame a, frame b), uint32
    skipped: tuple

    def use(self, source_id):
        self.document.require_open()
        pos = int(np.searchsorted(self.uses[:, 0], source_id))
        if pos >= len(self.uses) or self.uses[pos, 0] != source_id:
            raise ValueError('source primitive is not factored')
        source, prototype, a, b = map(int, self.uses[pos])
        return AnalyticUse(source, prototype, (a, b) if self.prototypes[prototype].kind == 'LINE' else (a,))

    def statistics(self):
        instances = Counter(self.prototypes[int(p)].kind for p in self.uses[:, 1])
        shapes = Counter(p.kind for p in self.prototypes)
        return {'source_primitive_uses': len(self.uses), 'intrinsic_shape_definitions': len(self.prototypes),
                'packed_use_array_bytes': self.uses.nbytes, 'skipped': list(self.skipped),
                'by_type': {kind: {'uses': n, 'intrinsic_shapes': shapes[kind]} for kind, n in sorted(instances.items())}}


@dataclass(frozen=True)
class AffineUse:
    """Original analytic use with exact local scale and unchanged parameterization."""
    source_id: int
    prototype: int
    frame_source_ids: tuple
    local_scale: tuple


@dataclass(frozen=True)
class AffineCatalog:
    """Unit analytic shapes with per-use exact scales, never pre-triangulated meshes."""
    document: object
    prototypes: tuple
    scales: tuple
    uses: object  # sorted source, prototype, frame a, frame b, scale id

    def use(self, source_id):
        self.document.require_open()
        pos = int(np.searchsorted(self.uses[:, 0], source_id))
        if pos >= len(self.uses) or self.uses[pos, 0] != source_id:
            raise ValueError('source primitive is not affine-factored')
        source, prototype, a, b, scale = map(int, self.uses[pos])
        frames = (a, b) if self.prototypes[prototype].kind == 'LINE' else (a,)
        return AffineUse(source, prototype, frames, self.scales[scale])

    def statistics(self):
        instances = Counter(self.prototypes[int(p)].kind for p in self.uses[:, 1])
        shapes = Counter(p.kind for p in self.prototypes)
        return {'source_primitive_uses': len(self.uses), 'shape_definitions': len(self.prototypes),
                'exact_scale_profiles': len(self.scales), 'packed_use_array_bytes': self.uses.nbytes,
                'by_type': {kind: {'uses': n, 'shapes': shapes[kind]} for kind, n in sorted(instances.items())}}


def factor_affine_primitives(catalog):
    """Normalize circles/ellipses, cylinders and spheres to unit analytic shapes.

    Circle/ellipse scale is (a,b,1), cylinder scale is (r,r,1), and sphere scale
    is (r,r,r). Keeping cylinder z scale 1 preserves its axial v parameter.
    Cones/tori stay dimensioned rigid prototypes. All exact source scalars,
    original frames, curve/surface parameters and parent trims remain available.
    """
    one = '~R1E0'; prototypes = {}; scales = {}; uses = []
    for source, pid, a, b in catalog.uses:
        original = catalog.prototypes[int(pid)]; kind = original.kind
        scale = (one,) * original.dimension; prototype = original
        if kind in ('CIRCLE', 'ELLIPSE'):
            r = original.parameters[0]; other = original.parameters[1] if kind == 'ELLIPSE' else r
            scale = (r, other) + ((one,) if original.dimension == 3 else ())
            prototype = AnalyticPrototype('UNIT_CIRCLE', original.dimension, ())
        elif kind == 'CYLINDRICAL_SURFACE':
            r = original.parameters[0]; scale = (r, r, one)
            prototype = AnalyticPrototype('UNIT_CYLINDER', 3, ())
        elif kind == 'SPHERICAL_SURFACE':
            scale = (original.parameters[0],) * 3
            prototype = AnalyticPrototype('UNIT_SPHERE', 3, ())
        target = prototypes.setdefault(prototype, len(prototypes))
        sid = scales.setdefault(scale, len(scales))
        uses.append((int(source), target, int(a), int(b), sid))
    return AffineCatalog(catalog.document, tuple(prototypes), tuple(scales), readonly(uses, np.uint32).reshape(-1, 5))


def factor_analytic_frames(pool):
    """Factor simple analytic primitives symbolically, without float matrices/fits."""
    ix = pool.document.index; prototypes = {}; uses = []; skipped = []
    for row in ix.rows_of(*PARAMETER_COUNTS):
        row = int(row)
        if pool.source_to_recipe[row] < 0:
            continue
        kind = ix.tname(row); eid = int(ix.ids[row])
        record = canonical_record(ix, row, lambda v: v, decimals=True, display_names=True)
        parts = record[len(kind)+1:-2].split(b',')
        frames = 2 if kind == 'LINE' else 1
        if len(parts) != 1 + frames + PARAMETER_COUNTS[kind] or parts[0] != b"''" or any(re.fullmatch(rb'#\d+', p) is None for p in parts[1:1+frames]):
            skipped.append((eid, 'unsupported analytic argument schema')); continue
        ids = tuple(int(p[1:]) for p in parts[1:1+frames])
        scalars = parts[1+frames:]
        scalar_pattern = rb'~(?:I-?\d+|R-?\d+E-?\d+)'
        if any(re.fullmatch(scalar_pattern, value) is None for value in scalars):
            skipped.append((eid, 'unsupported analytic scalar schema')); continue
        if kind == 'LINE':
            # LINE's point and VECTOR are kept, including VECTOR magnitude and
            # direction ratios. They are not reduced to a direction-only pose.
            point = canonical_record(ix, ix.r(ids[0]), lambda v: v, decimals=True, display_names=True) if ix.r(ids[0]) >= 0 else b''
            match = re.fullmatch(rb"CARTESIAN_POINT\('',\(([^()]*)\)\);", point)
            dimension = len(match.group(1).split(b',')) if match else 0
            valid = dimension in (2, 3) and ix.r(ids[1]) >= 0 and ix.tname(ix.r(ids[1])) == 'VECTOR'
        else:
            frame_kind = ix.tname(ix.r(ids[0])) if ix.r(ids[0]) >= 0 else ''
            dimension = 3 if frame_kind == 'AXIS2_PLACEMENT_3D' else 2 if frame_kind == 'AXIS2_PLACEMENT_2D' else 0
            valid = dimension == 3 or (dimension == 2 and kind in ('CIRCLE', 'ELLIPSE'))
        if not valid:
            skipped.append((eid, 'unsupported analytic placement schema')); continue
        # These schema slots are REALs, unlike generic token slots where an
        # INTEGER must remain distinct. Radius 1 and 1.0 mean the same shape.
        parameters = tuple((b'~R' + p[2:] + b'E0' if p.startswith(b'~I') else p).decode('ascii') for p in scalars)
        prototype = AnalyticPrototype(kind, dimension, parameters)
        pid = prototypes.setdefault(prototype, len(prototypes))
        uses.append((eid, pid, ids[0], ids[1] if frames == 2 else 0))
    uses.sort()
    return AnalyticCatalog(pool.document, tuple(prototypes), readonly(uses, np.uint32).reshape(-1, 4), tuple(skipped))


@dataclass(frozen=True)
class OptimizerIR:
    """Source-backed optimizer checkpoint with distinct sharing and ownership views."""
    document: object
    geometry: RecipePool
    appearance: RecipePool
    analytic: AnalyticCatalog
    affine: AffineCatalog
    units: bytes
    source_hierarchy: bytes | None = None

    def affine_patch_instances(self, *, roles=None, budget_mm=1e-6):
        """Factor eligible finite faces into quad/triangle affine uses plus fallbacks.

        Dimensions, source topology, appearance targets, component ownership and
        marking roles remain independent per use. Native validation is a later
        promotion gate; this bounds source straight-boundary normalization only.
        """
        from cad_patch_instances import build_patch_instances
        if self.source_hierarchy is None:
            raise ValueError('affine patch instances require a reviewed hierarchy')
        return build_patch_instances(self.document,json.loads(self.source_hierarchy),roles=roles,budget_mm=budget_mm)

    def collision_roles(self, path):
        """Bind visual-only markings to this source and its reviewed hierarchy.

        Whole marking solids produce no collision. Embedded markings require
        separately owned backing coverage; source topology stays available.
        """
        from cad_collision_roles import CollisionRoles
        if self.source_hierarchy is None:
            raise ValueError('collision roles require a reviewed hierarchy')
        if json.loads(self.source_hierarchy)['files_sha256']['field.step'] != self.document.source_sha256:
            raise ValueError('optimizer hierarchy/source mismatch')
        return CollisionRoles(json.loads(Path(path).read_bytes()), json.loads(self.source_hierarchy),
                              hierarchy_sha256=hashlib.sha256(self.source_hierarchy).hexdigest())

    def component(self, body_id):
        """Bind one reachable closed plane/extrusion body to source surface uses.

        Complete faces, loops, shared edge ownership and finite curve trims are
        retained. Native meshing/export is provided by cad_component separately.
        """
        from cad_component import component_graph
        self.geometry.recipe_for_source(body_id)
        return component_graph(self.document,body_id)

    def vector_layer(self, findings, *, policy=None):
        """Build selected parametric curves with automatic fits and source fallbacks.

        Only reachable source edges are admitted. Portable selections retain
        original spline parameters and re-tessellate to a requested length error.
        """
        from cad_vector_ir import build_vector_ir
        for entry in findings['curve_examples']:
            self.geometry.recipe_for_source(entry['source_edge_id'])
        for entry in findings.get('polygon_examples_first_40',[]):
            self.geometry.recipe_for_source(entry['source_face_id'])
        return build_vector_ir(self.document,findings,policy=policy)

    def polygon_patch(self, face_id):
        """Decode one reachable finite straight-boundary planar face for matching.

        Curved edges, holes and unsupported source topology fail explicitly.
        Exact congruence and approximate discovery remain separate operations.
        """
        from cad_patch_matching import polygon_patch
        self.geometry.recipe_for_source(face_id)
        return polygon_patch(self.document,face_id)

    def structural_views(self):
        """Build typed operands, explicit topology and stable geometry identities.

        Kept opt-in because the full source has millions of recipes. Results
        remain source-backed and are not a standalone CAD serialization.
        """
        from cad_ir_structure import build_structural_views
        return build_structural_views(self)

    def body_uses(self):
        """Yield original body ownership/placement plus its shared construction recipe."""
        for body in CadScene(self.document).occurrences():
            yield body, self.geometry.recipe_for_source(body.source_body_id)

    def style_bindings(self):
        """Yield original binding/target IDs and independently shared style recipes."""
        for binding, target, assignments in CadScene(self.document).style_bindings():
            yield binding, target, tuple(self.appearance.recipe_for_source(v) for v in assignments)

    def validate(self):
        geometry = self.geometry.validate(); appearance = self.appearance.validate()
        # Re-derive every supported analytic use from source; no rounded frame
        # matching is allowed into this checkpoint.
        catalog = factor_analytic_frames(self.geometry)
        if catalog.prototypes != self.analytic.prototypes or not np.array_equal(catalog.uses, self.analytic.uses) or catalog.skipped != self.analytic.skipped:
            raise ValueError('analytic construction changed')
        affine = factor_affine_primitives(catalog)
        if affine.prototypes != self.affine.prototypes or affine.scales != self.affine.scales or not np.array_equal(affine.uses, self.affine.uses):
            raise ValueError('affine normalization changed')
        self.document.verify_source()
        return {'geometry_records_checked': geometry, 'appearance_records_checked': appearance,
                'analytic_uses_checked': len(catalog.uses),
                'affine_uses_checked': len(affine.uses),
                'body_occurrences_retained': sum(1 for _ in self.body_uses()),
                'style_bindings_retained': sum(1 for _ in self.style_bindings()),
                'original_topology_incidence_retained': True, 'source_unchanged': True}


def build_optimizer_ir(document, *, normalize_decimals=False, normalize_directions=False, hierarchy=None):
    """Build a fresh immutable IR; source/native CAD and runtime exports stay intact."""
    document.require_open(); document.verify_source()
    units = unit_profile(document)
    catalog = Path(hierarchy).read_bytes() if hierarchy is not None else None
    if catalog is not None and json.loads(catalog).get('files_sha256', {}).get('field.step') != document.source_sha256:
        raise ValueError('hierarchy catalog/input STEP hash mismatch')
    geometry = build_pool(document, [b for b, _ in document.model.bodies], decimals=normalize_decimals, display_names=True, directions=normalize_directions)
    appearance = build_pool(document, document.index.rows_of('PRESENTATION_STYLE_ASSIGNMENT'), decimals=normalize_decimals, display_names=False)
    analytic = factor_analytic_frames(geometry)
    result = OptimizerIR(document, geometry, appearance, analytic, factor_affine_primitives(analytic),
                         json.dumps(units, sort_keys=True).encode(), catalog)
    document.verify_source()
    return result
