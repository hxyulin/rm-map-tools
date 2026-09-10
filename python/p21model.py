#!/usr/bin/env python3
"""Product / assembly / body / style model on top of a p21index Index.

Everything here works on index rows (positions in the index arrays), not
entity ids; `ix.ids[row]` gives the id, `ix.r(id)` the row.
"""
import re, collections
import numpy as np
from p21index import Index

BODY_TYPES = ('MANIFOLD_SOLID_BREP', 'BREP_WITH_VOIDS', 'SHELL_BASED_SURFACE_MODEL', 'FACETED_BREP')
REP_TYPES = ('ADVANCED_BREP_SHAPE_REPRESENTATION', 'MANIFOLD_SURFACE_SHAPE_REPRESENTATION',
             'SHAPE_REPRESENTATION', 'FACETED_BREP_SHAPE_REPRESENTATION',
             'GEOMETRICALLY_BOUNDED_SURFACE_SHAPE_REPRESENTATION',
             'GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION')
TOPO = ('CLOSED_SHELL', 'OPEN_SHELL', 'ORIENTED_CLOSED_SHELL', 'ORIENTED_OPEN_SHELL',
        'SHELL_BASED_SURFACE_MODEL', 'BREP_WITH_VOIDS', 'MANIFOLD_SOLID_BREP', 'FACETED_BREP',
        'FACE_OUTER_BOUND', 'FACE_BOUND', 'EDGE_LOOP', 'ORIENTED_EDGE', 'EDGE_CURVE',
        'VERTEX_POINT', 'VERTEX_LOOP', 'ORIENTED_FACE')
STR_RE = re.compile(rb"'((?:[^']|'')*)'")
NUM_RE = re.compile(rb'[-+0-9.Ee]+')
X2_RE = re.compile(r'\\X2\\([0-9A-F]+)\\X0\\')
X_RE = re.compile(r'\\X\\([0-9A-F]{2})')


def decode_p21(s: bytes) -> str:
    t = s.decode('ascii', errors='replace').replace("''", "'")
    t = X2_RE.sub(lambda m: bytes.fromhex(m.group(1)).decode('utf-16-be'), t)
    t = X_RE.sub(lambda m: chr(int(m.group(1), 16)), t)
    return t


def first_string(args: bytes):
    m = STR_RE.match(args)
    return decode_p21(m.group(1)) if m else None


class Model:
    def __init__(self, ix: Index):
        self.ix = ix
        T = ix.types; tid = ix.tid
        get = lambda n: tid.get(n, -1)
        self.t_face = get('ADVANCED_FACE')
        self.t_topo = {get(n) for n in TOPO} - {-1}
        self.t_body = {get(n) for n in BODY_TYPES} - {-1}
        self.t_rep = {get(n) for n in REP_TYPES} - {-1}
        self.t_cplx = get('CPLX')
        self.t_vertex = get('VERTEX_POINT')
        self.t_point = get('CARTESIAN_POINT')
        self.t_colour = get('COLOUR_RGB'); self.t_predef = get('DRAUGHTING_PRE_DEFINED_COLOUR')
        self.t_curve_style = get('CURVE_STYLE'); self.t_surf_usage = get('SURFACE_STYLE_USAGE')
        R = lambda row: ix.refs_of(row)
        # complex instances: which of them are shape representations
        self.cplx_rep = set()
        for row in ix.rows_of('CPLX'):
            t = ix.text(row)
            if b'SHAPE_REPRESENTATION(' in t and b'RELATIONSHIP' not in t:
                self.cplx_rep.add(row)
        # products
        self.product_name = {}
        for row in ix.rows_of('PRODUCT'):
            self.product_name[row] = first_string(ix.args(row))
        self.pdf_product = {}
        for row in ix.rows_of('PRODUCT_DEFINITION_FORMATION',
                              'PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE'):
            for rf in R(row):
                pr = ix.r(int(rf))
                if pr in self.product_name:
                    self.pdf_product[row] = pr; break
        self.pd_product = {}
        for row in ix.rows_of('PRODUCT_DEFINITION', 'PRODUCT_DEFINITION_WITH_ASSOCIATED_DOCUMENTS'):
            for rf in R(row):
                pr = ix.r(int(rf))
                if pr in self.pdf_product:
                    self.pd_product[row] = self.pdf_product[pr]; break
        self.pds_pd = {}
        for row in ix.rows_of('PRODUCT_DEFINITION_SHAPE'):
            rf = R(row)
            if len(rf):
                pr = ix.r(int(rf[0]))
                if pr in self.pd_product:
                    self.pds_pd[row] = pr
        # representations -> product
        self.rep_product = {}
        self.sdr_rows = {}
        for row in ix.rows_of('SHAPE_DEFINITION_REPRESENTATION'):
            rf = R(row)
            pds, rep = ix.r(int(rf[0])), ix.r(int(rf[1]))
            if pds in self.pds_pd:
                self.rep_product[rep] = self.pd_product[self.pds_pd[pds]]
                self.sdr_rows[rep] = row
        self.srr_rows = []
        for row in ix.rows_of('SHAPE_REPRESENTATION_RELATIONSHIP'):
            rf = R(row)
            r1, r2 = ix.r(int(rf[0])), ix.r(int(rf[1]))
            self.srr_rows.append((row, r1, r2))
        changed = True
        while changed:
            changed = False
            for row, r1, r2 in self.srr_rows:
                if r1 in self.rep_product and r2 not in self.rep_product:
                    self.rep_product[r2] = self.rep_product[r1]; changed = True
                elif r2 in self.rep_product and r1 not in self.rep_product:
                    self.rep_product[r1] = self.rep_product[r2]; changed = True
        self.product_reps = collections.defaultdict(list)
        for rep, p in self.rep_product.items():
            self.product_reps[p].append(rep)
        # assembly tree: NAUO -> (parent product, child product)
        self.children = collections.defaultdict(list)
        self.nauo = {}
        for row in ix.rows_of('NEXT_ASSEMBLY_USAGE_OCCURRENCE'):
            rf = R(row)
            pa, ch = self.pd_product.get(ix.r(int(rf[0]))), self.pd_product.get(ix.r(int(rf[1])))
            self.nauo[row] = (pa, ch)
            self.children[pa].append((row, ch))
        kids = {c for v in self.children.values() for _, c in v}
        self.roots = [p for p in self.product_name if p not in kids and (p in self.children or p in self.product_reps)]
        # bodies: (body_row, rep_row)
        self.bodies = []
        self.body_rep = {}
        for rep in list(self.product_reps.values()):
            pass
        rep_rows = set(ix.rows_of(*REP_TYPES).tolist()) | self.cplx_rep
        for rep in sorted(rep_rows):
            for rf in R(rep):
                b = ix.r(int(rf))
                if b >= 0 and T[b] in self.t_body:
                    self.bodies.append((b, rep)); self.body_rep[b] = rep
        self._ckey = {}; self.colour_names = {}
        # styles: target row -> (surface colour, curve colour, style row)
        self.style_of_target = collections.defaultdict(list)
        self.styled = {}
        for row in ix.rows_of('STYLED_ITEM', 'OVER_RIDING_STYLED_ITEM'):
            rf = R(row)
            over = ix.tname(row) == 'OVER_RIDING_STYLED_ITEM'
            tgt = ix.r(int(rf[-2] if over else rf[-1]))
            styles = [ix.r(int(x)) for x in (rf[:-2] if over else rf[:-1])]
            surf, curve = self._colours(styles)
            self.styled[row] = (tgt, surf, curve, over)
            self.style_of_target[tgt].append(row)
        self._pts = {}

    # ---- colours -------------------------------------------------------
    PREDEF = {'red': (1, 0, 0), 'green': (0, 1, 0), 'blue': (0, 0, 1), 'yellow': (1, 1, 0),
              'magenta': (1, 0, 1), 'cyan': (0, 1, 1), 'black': (0, 0, 0), 'white': (1, 1, 1)}

    def _colour_name(self, row, depth=0):
        """canonical colour key 'r,g,b' (4 decimals); names recorded in self.colour_names."""
        ix = self.ix; t = ix.types[row]
        if t == self.t_colour or t == self.t_predef:
            k = self._ckey.get(row)
            if k is None:
                a = ix.args(row); name = first_string(a)
                if t == self.t_colour:
                    m = STR_RE.match(a)
                    rgb = tuple(float(x) for x in NUM_RE.findall(a[m.end():])[:3])
                else:
                    rgb = self.PREDEF.get(name, (0, 0, 0))
                k = ','.join(f'{c:.4f}' for c in rgb)
                self._ckey[row] = k
                self.colour_names.setdefault(k, set()).add(name or '')
            return k
        if depth > 8:
            return None
        for rf in ix.refs_of(row):
            c = self._colour_name(ix.r(int(rf)), depth + 1)
            if c is not None:
                return c
        return None

    def _colours(self, style_rows):
        """(surface colour, curve colour) reachable from PRESENTATION_STYLE_ASSIGNMENT rows."""
        ix = self.ix; curve = None; front = back = None
        # breadth-first in file order; a face may carry a .POSITIVE. and a
        # .NEGATIVE. SURFACE_STYLE_USAGE (two-sided colour): OCCT shows the front
        queue = list(style_rows); seen = set(); i = 0
        while i < len(queue):
            r = queue[i]; i += 1
            if r < 0 or r in seen:
                continue
            seen.add(r); t = ix.types[r]
            if t == self.t_surf_usage:
                side = ix.args(r).split(b',')[0].strip()
                c = self._colour_name(r)
                if side == b'.NEGATIVE.':
                    back = back or c
                else:
                    front = front or c
            elif t == self.t_curve_style:
                curve = curve or self._colour_name(r)
            else:
                queue.extend(ix.r(int(x)) for x in ix.refs_of(r))
        return front or back, curve

    def surface_colour(self, row):
        for s in self.style_of_target.get(row, ()):
            c = self.styled[s][1]
            if c:
                return c
        return None

    # ---- bodies -------------------------------------------------------
    def body_faces(self, body):
        """rows of ADVANCED_FACEs of a body (topology traversal only)."""
        return [f for f, _ in self.body_faces_shells(body)]

    def body_faces_shells(self, body):
        """[(face row, shell row)] of a body; shell row is the CLOSED/OPEN_SHELL owning the face."""
        ix = self.ix; out = []; stack = [(body, -1)]; seen = set()
        t_shell = {ix.tid.get(n, -1) for n in ('CLOSED_SHELL', 'OPEN_SHELL')} - {-1}
        while stack:
            r, sh = stack.pop()
            if r < 0 or r in seen:
                continue
            seen.add(r); t = ix.types[r]
            if t == self.t_face:
                out.append((r, sh))
            elif t in self.t_topo or t == self.t_cplx:
                if t in t_shell:
                    sh = r
                stack.extend((ix.r(int(x)), sh) for x in ix.refs_of(r))
        return out

    def extra_outer_bounds(self, faces):
        """faces with several FACE_OUTER_BOUNDs get split by OCCT's ShapeFix; count the extras."""
        ix = self.ix; t_ob = ix.tid.get('FACE_OUTER_BOUND', -1); extra = 0
        for f in faces:
            ob = sum(1 for x in ix.refs_of(f)[:-1] if ix.types[ix.r(int(x))] == t_ob)
            if ob > 1:
                extra += ob - 1
        return extra

    def point(self, row):
        p = self._pts.get(row)
        if p is None:
            a = self.ix.args(row)
            nums = a[a.index(b'('):]
            p = tuple(float(x) for x in NUM_RE.findall(nums)[:3])
            self._pts[row] = p
        return p

    def body_bbox(self, body, faces=None):
        """bbox from vertex points (part-local mm). Returns (min, max, nverts)."""
        ix = self.ix; stack = [body]; seen = set(); pts = []
        while stack:
            r = stack.pop()
            if r < 0 or r in seen:
                continue
            seen.add(r); t = ix.types[r]
            if t == self.t_face:
                stack.extend(ix.r(int(x)) for x in ix.refs_of(r)[:-1])
            elif t == self.t_vertex:
                for x in ix.refs_of(r):
                    pr = ix.r(int(x))
                    if pr >= 0 and ix.types[pr] == self.t_point:
                        pts.append(self.point(pr))
            elif t in self.t_topo or t == self.t_cplx:
                stack.extend(ix.r(int(x)) for x in ix.refs_of(r))
        if not pts:
            return None, None, 0
        a = np.array(pts)
        return a.min(0), a.max(0), len(pts)

    def face_colour_hist(self, body, faces=None):
        """effective face colours: face style, else shell style, else body style."""
        bc = self.surface_colour(body)
        return collections.Counter(self.surface_colour(f) or self.surface_colour(sh) or bc
                                   for f, sh in self.body_faces_shells(body))

    def body_product(self, body):
        return self.rep_product.get(self.body_rep.get(body))

    def pname(self, p):
        return self.product_name.get(p, '?')
