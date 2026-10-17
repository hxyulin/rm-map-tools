# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Packed source topology, typed recipe operands and versioned cache identities.

Hashes describe ordered construction graphs, not geometric congruence. Unknown
STEP syntax remains opaque bytes; no parameters are converted to binary floats.
"""
from array import array
from dataclasses import dataclass
import hashlib
import json
import re

import numpy as np
from audit_geometry_duplicates import GeometryFingerprints
from cad_optimizer import TOKEN, canonical_record, readonly

TOPOLOGY_TYPES = frozenset('VERTEX_POINT EDGE_CURVE ORIENTED_EDGE EDGE_LOOP VERTEX_LOOP FACE_BOUND FACE_OUTER_BOUND ADVANCED_FACE FACE_SURFACE OPEN_SHELL CLOSED_SHELL ORIENTED_CLOSED_SHELL SHELL_BASED_SURFACE_MODEL MANIFOLD_SOLID_BREP BREP_WITH_VOIDS FACETED_BREP'.split())
# Quoted/binary values and comments must be consumed before interpreting refs.
OPERAND = re.compile(rb"'(?:[^']|'')*'|\"[^\"]*\"|#[0-9]+|~[IRQ]-?[0-9]+(?:E-?[0-9]+)?|(?<![A-Za-z0-9_])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?|\.[A-Z_]+\.|\$|\*")
REFERENCE, INTEGER, REAL, STRING, BINARY, ENUM, OMITTED, DERIVED, EXACT = range(9)


@dataclass(frozen=True)
class TypedRecords:
    """CSR operands plus interned exact lexemes and grouping-preserving syntax.

    Reference values address recipes; all other values address lexemes. Syntax
    segments retain commas/parentheses and unknown bytes for exact reconstruction.
    """
    offsets: object
    tags: object
    values: object
    lexemes: tuple
    syntax: bytes
    syntax_offsets: object

    def reconstruct(self, recipe):
        start, end = map(int, self.offsets[recipe:recipe+2])
        parts = [self.syntax[int(self.syntax_offsets[i]):int(self.syntax_offsets[i+1])]
                 for i in range(start+recipe,end+recipe+1)]
        result = [parts[0]]
        for slot, suffix in zip(range(start, end), parts[1:]):
            value = int(self.values[slot])
            result.extend((b'#'+str(value).encode() if self.tags[slot] == REFERENCE else self.lexemes[value], suffix))
        return b''.join(result)

    def statistics(self):
        return {'records': len(self.offsets)-1, 'operands': len(self.tags),
                'reference_operands': int(np.count_nonzero(self.tags == REFERENCE)),
                'array_bytes': self.offsets.nbytes+self.tags.nbytes+self.values.nbytes+self.syntax_offsets.nbytes,
                'lexeme_bytes': sum(map(len,self.lexemes)),
                'syntax_bytes': len(self.syntax)}


def typed_records(pool):
    """Decode recipe operands without losing exact decimal spellings or structure."""
    offsets=array('Q',[0]); tags=array('B'); values=array('I'); lexemes=[]; intern={}; syntax=bytearray(); syntax_offsets=array('Q',[0])
    for recipe in range(len(pool.kinds)):
        record=pool.record(recipe); previous=0
        for match in OPERAND.finditer(record):
            token=match.group(); syntax.extend(record[previous:match.start()]); syntax_offsets.append(len(syntax)); previous=match.end()
            if token.startswith(b'#'):
                tag=REFERENCE; value=int(token[1:])
                if value >= len(pool.kinds): raise ValueError('unresolved typed recipe reference')
            else:
                if token.startswith(b"'"): tag=STRING
                elif token.startswith(b'"'): tag=BINARY
                elif token.startswith(b'~'): tag=EXACT
                elif token == b'$': tag=OMITTED
                elif token == b'*': tag=DERIVED
                elif token.startswith(b'.') and token.endswith(b'.') and token[1:2].isalpha(): tag=ENUM
                else: tag=REAL if b'.' in token or b'e' in token.lower() else INTEGER
                value=intern.get(token)
                if value is None:
                    value=len(lexemes);intern[token]=value;lexemes.append(token)
            tags.append(tag);values.append(value)
        syntax.extend(record[previous:]); syntax_offsets.append(len(syntax));offsets.append(len(tags))
    return TypedRecords(readonly(offsets,np.uint64),readonly(tags,np.uint8),
                        readonly(values,np.uint32),tuple(lexemes),bytes(syntax),readonly(syntax_offsets,np.uint64))


@dataclass(frozen=True)
class TopologyUse:
    """One original entity with schema roles for its ordered child uses."""
    source_id: int
    kind: str
    recipe: int
    references: tuple
    orientation: bool | None

    def roles(self):
        """Expose common B-rep roles; unknown forms retain ordered references.

        Oriented-edge endpoints are derived in STEP, so the single child is
        its underlying edge. UV/pcurve details live under the curve/surface
        reference, rather than being approximated by a polygon here.
        """
        refs=self.references
        if self.kind == 'VERTEX_POINT' and len(refs)==1:return {'point':refs[0]}
        if self.kind == 'EDGE_CURVE' and len(refs)==3:
            return dict(zip(('start_vertex','end_vertex','curve'),refs))
        if self.kind == 'ORIENTED_EDGE' and len(refs)==1:return {'edge':refs[0]}
        if self.kind in ('FACE_BOUND','FACE_OUTER_BOUND') and len(refs)==1:return {'loop':refs[0]}
        if self.kind in ('ADVANCED_FACE','FACE_SURFACE') and refs:
            return {'bounds':refs[:-1],'surface':refs[-1]}
        if self.kind == 'EDGE_LOOP':return {'oriented_edges':refs}
        if self.kind in ('OPEN_SHELL','CLOSED_SHELL'):return {'faces':refs}
        return {'ordered_references':refs}


@dataclass(frozen=True)
class TopologyUses:
    """Original topology entities and ordered source references, never welded.

    Edges retain start/end/curve references, loops retain repeated oriented-edge
    uses, bounds retain loop orientation, and faces retain surface and sense.
    Surface/curve references lead to source UV trims/pcurves where present.
    Scalars and complete schema remain in typed records addressed by recipe.
    """
    source_ids: object
    kinds: object
    type_names: tuple
    recipes: object
    offsets: object
    references: object
    orientations: object  # -1 absent/not simple, 0 false, 1 true

    def use(self, source_id):
        """Resolve a source identity into a typed face/loop/edge/vertex use."""
        refs=self.children(source_id)
        pos=int(np.searchsorted(self.source_ids,source_id))
        sense=int(self.orientations[pos])
        return TopologyUse(source_id,self.type_names[int(self.kinds[pos])],int(self.recipes[pos]),
                           tuple(map(int,refs)),None if sense<0 else bool(sense))

    def children(self, source_id):
        pos=int(np.searchsorted(self.source_ids,source_id))
        if pos == len(self.source_ids) or self.source_ids[pos] != source_id:
            raise ValueError('not a topology use')
        return self.references[int(self.offsets[pos]):int(self.offsets[pos+1])]

    def statistics(self):
        return {'entities':len(self.source_ids),'ordered_references':len(self.references),
                'explicit_orientations':int(np.count_nonzero(self.orientations>=0)),
                'array_bytes':sum(v.nbytes for v in (self.source_ids,self.kinds,self.recipes,self.offsets,self.references,self.orientations))}


def topology_uses(pool):
    ix=pool.document.index; ids=[];kinds=[];recipes=[];offsets=[0];refs=[];orientations=[]
    rows=np.flatnonzero(pool.source_to_recipe>=0)
    for row in rows:
        if ix.tname(int(row)) not in TOPOLOGY_TYPES: continue
        ids.append(int(ix.ids[row]));kinds.append(int(ix.types[row]));recipes.append(int(pool.source_to_recipe[row]))
        refs.extend(map(int,ix.refs_of(int(row))));offsets.append(len(refs))
        text=canonical_record(ix,int(row),lambda value:value,decimals=False,display_names=True)
        match=re.search(rb',\.(T|F)\.\);$',text)
        orientations.append(-1 if match is None else int(match.group(1)==b'T'))
    order=np.argsort(ids)
    # Index rows are normally source-ID ordered; retain a deterministic public lookup.
    sorted_refs=[];sorted_offsets=[0]
    for pos in order:
        sorted_refs.extend(refs[offsets[pos]:offsets[pos+1]]);sorted_offsets.append(len(sorted_refs))
    return TopologyUses(readonly(np.asarray(ids)[order],np.uint64),readonly(np.asarray(kinds)[order],np.uint16),tuple(ix.typenames),readonly(np.asarray(recipes)[order],np.uint32),
                        readonly(sorted_offsets,np.uint64),readonly(sorted_refs,np.uint64),
                        readonly(np.asarray(orientations)[order],np.int8))


def cache_context(document):
    """Stable context identity includes complete assigned units and uncertainties.

    No source IDs, placements or effective appearance are implied by this key.
    Those remain separate cache dimensions for later tessellation passes.
    """
    ix=document.index; hashes=GeometryFingerprints(ix,ignore_display_names=True)
    contexts=[]
    for row in ix.rows_of('CPLX'):
        text=TOKEN.sub(lambda m:b'' if m.group().startswith((b"'",b'/*')) else m.group(),ix.text(int(row)))
        if b'GEOMETRIC_REPRESENTATION_CONTEXT' in text:
            contexts.append(hashes.signature(int(row)).hex())
    return hashlib.sha256(json.dumps(sorted(set(contexts))).encode()).digest()


def stable_recipe_hashes(pool, context):
    """Merkle keys independent of source IDs, recipe numbering and root order.

    These keys intentionally omit incidence identity; use incidence_hash before
    sharing a complete body. SHA-256 matches still require equality verification.
    """
    prefix=b'rm-ir-recipe-v1\0'+context+bytes((pool.normalize_decimals,pool.remove_display_names,pool.normalize_directions))
    hashes=[]
    for recipe in range(len(pool.kinds)):
        def replace(match):
            if match.group(1) is None:return match.group()
            child=int(match.group(1))
            if child >= recipe:raise ValueError('recipe graph is not child-first')
            return b'#'+hashes[child].hex().encode()
        record=TOKEN.sub(replace,pool.record(recipe))
        hashes.append(hashlib.sha256(prefix+record).digest())
    return readonly(np.frombuffer(b''.join(hashes),dtype=np.uint8).reshape(-1,32))


def incidence_hash(pool, root_id, context):
    """Hash an ordered rooted source graph with explicit alias/backreference IDs.

    First-visit ordinals replace source IDs, preserving repeated incidence and
    separating coincident-but-distinct vertices. This is conservative ordered
    graph identity, not an isomorphism search or a congruence certificate.
    """
    ix=pool.document.index; seen={}; pending=[root_id]
    digest=hashlib.sha256(b'rm-ir-incidence-v1\0'+context+bytes((pool.normalize_decimals,pool.remove_display_names,pool.normalize_directions)))
    while pending:
        entity=pending.pop()
        if entity in seen:
            digest.update(b'R'+str(seen[entity]).encode()+b';');continue
        pool.recipe_for_source(entity)
        ordinal=len(seen);seen[entity]=ordinal;children=[]
        def resolve(value):
            children.append(value)
            return len(children)-1
        record=canonical_record(ix,ix.r(entity),resolve,decimals=pool.normalize_decimals,
                                display_names=pool.remove_display_names,directions=pool.normalize_directions)
        digest.update(b'N'+str(ordinal).encode()+b':'+str(len(record)).encode()+b':'+record)
        pending.extend(reversed(children))
    return digest.hexdigest()


@dataclass(frozen=True)
class PassContract:
    """Reviewable prerequisites, guarantees, correspondence and savings metric."""
    name: str
    requires: tuple
    preserves: tuple
    correspondence: str
    metric: str


PASS_CONTRACTS = (
    PassContract('intern-ordered-recipes-v1',('acyclic resolved source graph','single explicit unit profile'),
                 ('source identity','ordered incidence','placements','appearance','unknown metadata'),
                 'source entity ID to recipe ID; not a topology equivalence certificate','recipe definitions and bytes'),
    PassContract('typed-operands-v1',('canonical recipe grammar',),('every recipe byte','exact scalar lexemes','reference order'),
                 'recipe and operand slot to tag/value/syntax segment','array, lexeme and syntax bytes; Python overhead separate'),
    PassContract('topology-uses-v1',('source-backed geometry pool',),('ordered source references','orientation','distinct coincident entities'),
                 'source topology ID to recipe, ordered children and sense','topology entities, reference uses and packed bytes'),
    PassContract('stable-identities-v1',('complete context graphs','child-first recipe DAG'),
                 ('source-number independent keys','ordered graph alias patterns in incidence keys'),
                 'recipe to Merkle key; rooted body to incidence key; verify equality before reuse','candidate groups only; no geometry or triangle savings'),
)


@dataclass(frozen=True)
class StructuralViews:
    """Optional typed geometry/topology views and scoped stable identities."""
    geometry: TypedRecords
    topology: TopologyUses
    context: bytes
    recipe_hashes: object
    body_hashes: tuple  # source ID, ordered incidence digest

    def validate(self, ir):
        """Reconstruct every recipe and recheck every original topology use."""
        for recipe in range(len(ir.geometry.kinds)):
            if self.geometry.reconstruct(recipe) != ir.geometry.record(recipe):
                raise ValueError('typed recipe reconstruction mismatch')
        expected=topology_uses(ir.geometry)
        for field in ('source_ids','kinds','recipes','offsets','references','orientations'):
            if not np.array_equal(getattr(self.topology,field),getattr(expected,field)):
                raise ValueError('topology use table mismatch: '+field)
        if self.topology.type_names != expected.type_names:
            raise ValueError('topology type names mismatch')
        if self.context != cache_context(ir.document):raise ValueError('context mismatch')
        if not np.array_equal(self.recipe_hashes,stable_recipe_hashes(ir.geometry,self.context)):
            raise ValueError('stable recipe hashes mismatch')
        roots=sorted({int(ir.document.index.ids[row]) for row,_ in ir.document.model.bodies})
        if [source for source,_ in self.body_hashes] != roots:
            raise ValueError('body root coverage mismatch')
        for source, digest in self.body_hashes:
            if digest != incidence_hash(ir.geometry,source,self.context):
                raise ValueError('body incidence hash mismatch')
        ir.document.verify_source()
        return {'typed_records_reconstructed':len(ir.geometry.kinds),
                'topology_uses_checked':len(self.topology.source_ids),
                'body_incidence_hashes_checked':len(self.body_hashes),'source_unchanged':True}


def build_structural_views(ir):
    """Materialize explicit source use tables; never mutate or export CAD."""
    context=cache_context(ir.document)
    roots=sorted({int(ir.document.index.ids[row]) for row,_ in ir.document.model.bodies})
    return StructuralViews(typed_records(ir.geometry),topology_uses(ir.geometry),context,
                           stable_recipe_hashes(ir.geometry,context),
                           tuple((source,incidence_hash(ir.geometry,source,context)) for source in roots))
