//! Product / assembly / body / style model over an [`Index`].
//!
//! Everything is expressed in index rows. The model mirrors the Python
//! prototype `prototype/p21model.py` whose numbers were validated against
//! OCCT; keep the two in step when changing traversal rules.

use std::collections::{BTreeSet, HashMap};

use crate::decode::{first_arg, first_string, leading_string, numbers};
use crate::index::{Index, Row};

/// Entity types that are bodies (children of a shape representation).
pub const BODY_TYPES: [&str; 4] = [
    "MANIFOLD_SOLID_BREP",
    "BREP_WITH_VOIDS",
    "SHELL_BASED_SURFACE_MODEL",
    "FACETED_BREP",
];
/// Shape representation types that can hold bodies.
pub const REP_TYPES: [&str; 6] = [
    "ADVANCED_BREP_SHAPE_REPRESENTATION",
    "MANIFOLD_SURFACE_SHAPE_REPRESENTATION",
    "SHAPE_REPRESENTATION",
    "FACETED_BREP_SHAPE_REPRESENTATION",
    "GEOMETRICALLY_BOUNDED_SURFACE_SHAPE_REPRESENTATION",
    "GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION",
];
/// Topology types traversed on the way from a body to its faces.
pub const TOPO_TYPES: [&str; 16] = [
    "CLOSED_SHELL",
    "OPEN_SHELL",
    "ORIENTED_CLOSED_SHELL",
    "ORIENTED_OPEN_SHELL",
    "SHELL_BASED_SURFACE_MODEL",
    "BREP_WITH_VOIDS",
    "MANIFOLD_SOLID_BREP",
    "FACETED_BREP",
    "FACE_OUTER_BOUND",
    "FACE_BOUND",
    "EDGE_LOOP",
    "ORIENTED_EDGE",
    "EDGE_CURVE",
    "VERTEX_POINT",
    "VERTEX_LOOP",
    "ORIENTED_FACE",
];

/// Interned colour: index into [`Model::colours`].
pub type ColourId = u32;

#[derive(Debug, Clone)]
pub struct Colour {
    /// Canonical key `r,g,b` with four decimals, the identity used everywhere.
    pub key: String,
    pub rgb: [f64; 3],
    /// Names the file gives this colour (`''` for unnamed).
    pub names: BTreeSet<String>,
}

#[derive(Debug, Clone, Copy)]
pub struct Styled {
    /// Styled geometry row (face, shell, body, curve), if it resolves.
    pub target: Option<Row>,
    pub surface: Option<ColourId>,
    pub curve: Option<ColourId>,
    pub overriding: bool,
}

#[derive(Debug, Clone, Copy)]
pub struct Occurrence {
    pub row: Row,
    pub parent: Option<Row>,
    pub child: Option<Row>,
}

/// Bounding box from vertex points, in the file's units (mm for DJI files).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BBox {
    pub min: [f64; 3],
    pub max: [f64; 3],
    pub vertices: usize,
}

pub struct Model<'a> {
    pub ix: &'a Index,
    t_face: u16,
    t_vertex: u16,
    t_point: u16,
    t_colour: u16,
    t_predef: u16,
    t_curve_style: u16,
    t_surf_usage: u16,
    t_cplx: u16,
    t_outer_bound: u16,
    is_topo: Vec<bool>,
    is_body: Vec<bool>,
    is_shell: Vec<bool>,
    /// Product rows in file order, and their names.
    pub products: Vec<Row>,
    pub product_name: HashMap<Row, String>,
    pub pdf_product: HashMap<Row, Row>,
    pub pd_product: HashMap<Row, Row>,
    pub pds_pd: HashMap<Row, Row>,
    /// Shape representation row -> owning product row.
    pub rep_product: HashMap<Row, Row>,
    /// Representation row -> its SHAPE_DEFINITION_REPRESENTATION row.
    pub sdr_of_rep: HashMap<Row, Row>,
    /// (SHAPE_REPRESENTATION_RELATIONSHIP row, rep 1, rep 2).
    pub srr: Vec<(Row, Option<Row>, Option<Row>)>,
    pub product_reps: HashMap<Row, Vec<Row>>,
    pub occurrences: Vec<Occurrence>,
    /// Parent product -> (occurrence row, child product).
    pub children: HashMap<Option<Row>, Vec<(Row, Option<Row>)>>,
    pub roots: Vec<Row>,
    /// (body row, representation row) in representation order.
    pub bodies: Vec<(Row, Row)>,
    pub body_rep: HashMap<Row, Row>,
    pub colours: Vec<Colour>,
    colour_ids: HashMap<String, ColourId>,
    colour_of_row: HashMap<Row, ColourId>,
    pub styled: HashMap<Row, Styled>,
    /// Styled geometry row -> style rows in file order.
    pub styles_of_target: HashMap<Row, Vec<Row>>,
}

/// Per-thread visited stamps for traversals (one u32 per entity, reused
/// across calls so a traversal allocates nothing).
struct Marks {
    stamp: Vec<u32>,
    generation: u32,
}

thread_local! {
    static MARKS: std::cell::RefCell<Marks> = const { std::cell::RefCell::new(Marks { stamp: Vec::new(), generation: 0 }) };
}

fn with_marks<R>(n: usize, f: impl FnOnce(&mut Marks) -> R) -> R {
    MARKS.with(|m| {
        let mut m = m.borrow_mut();
        if m.stamp.len() < n {
            m.stamp = vec![0; n];
            m.generation = 0;
        }
        m.begin();
        f(&mut m)
    })
}

impl Marks {
    fn begin(&mut self) {
        self.generation += 1;
        if self.generation == u32::MAX {
            self.stamp.iter_mut().for_each(|s| *s = 0);
            self.generation = 1;
        }
    }
    /// Returns true the first time `row` is seen in this generation.
    #[inline]
    fn visit(&mut self, row: Row) -> bool {
        let s = &mut self.stamp[row as usize];
        if *s == self.generation {
            false
        } else {
            *s = self.generation;
            true
        }
    }
}

const PREDEFINED: [(&str, [f64; 3]); 8] = [
    ("red", [1.0, 0.0, 0.0]),
    ("green", [0.0, 1.0, 0.0]),
    ("blue", [0.0, 0.0, 1.0]),
    ("yellow", [1.0, 1.0, 0.0]),
    ("magenta", [1.0, 0.0, 1.0]),
    ("cyan", [0.0, 1.0, 1.0]),
    ("black", [0.0, 0.0, 0.0]),
    ("white", [1.0, 1.0, 1.0]),
];

fn type_flags(ix: &Index, names: &[&str]) -> Vec<bool> {
    let mut v = vec![false; ix.type_names().len()];
    for n in names {
        if let Some(t) = ix.type_id(n) {
            v[t as usize] = true;
        }
    }
    v
}

impl<'a> Model<'a> {
    pub fn new(ix: &'a Index) -> Model<'a> {
        let t = |n: &str| ix.type_id(n).unwrap_or(u16::MAX);
        let mut m = Model {
            ix,
            t_face: t("ADVANCED_FACE"),
            t_vertex: t("VERTEX_POINT"),
            t_point: t("CARTESIAN_POINT"),
            t_colour: t("COLOUR_RGB"),
            t_predef: t("DRAUGHTING_PRE_DEFINED_COLOUR"),
            t_curve_style: t("CURVE_STYLE"),
            t_surf_usage: t("SURFACE_STYLE_USAGE"),
            t_cplx: t("CPLX"),
            t_outer_bound: t("FACE_OUTER_BOUND"),
            is_topo: type_flags(ix, &TOPO_TYPES),
            is_body: type_flags(ix, &BODY_TYPES),
            is_shell: type_flags(ix, &["CLOSED_SHELL", "OPEN_SHELL"]),
            products: Vec::new(),
            product_name: HashMap::new(),
            pdf_product: HashMap::new(),
            pd_product: HashMap::new(),
            pds_pd: HashMap::new(),
            rep_product: HashMap::new(),
            sdr_of_rep: HashMap::new(),
            srr: Vec::new(),
            product_reps: HashMap::new(),
            occurrences: Vec::new(),
            children: HashMap::new(),
            roots: Vec::new(),
            bodies: Vec::new(),
            body_rep: HashMap::new(),
            colours: Vec::new(),
            colour_ids: HashMap::new(),
            colour_of_row: HashMap::new(),
            styled: HashMap::new(),
            styles_of_target: HashMap::new(),
        };
        m.build_products();
        m.build_representations();
        m.build_assembly();
        m.build_bodies();
        m.build_styles();
        m
    }

    fn build_products(&mut self) {
        let ix = self.ix;
        for row in ix.rows_of(&["PRODUCT"]) {
            self.products.push(row);
            self.product_name
                .insert(row, first_string(ix.args(row)).unwrap_or_default());
        }
        for row in ix.rows_of(&[
            "PRODUCT_DEFINITION_FORMATION",
            "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE",
        ]) {
            if let Some(p) = ix
                .refs_of(row)
                .iter()
                .filter_map(|&r| ix.row(r))
                .find(|r| self.product_name.contains_key(r))
            {
                self.pdf_product.insert(row, p);
            }
        }
        for row in ix.rows_of(&[
            "PRODUCT_DEFINITION",
            "PRODUCT_DEFINITION_WITH_ASSOCIATED_DOCUMENTS",
        ]) {
            if let Some(p) = ix
                .refs_of(row)
                .iter()
                .filter_map(|&r| ix.row(r))
                .find_map(|r| self.pdf_product.get(&r))
            {
                self.pd_product.insert(row, *p);
            }
        }
        for row in ix.rows_of(&["PRODUCT_DEFINITION_SHAPE"]) {
            if let Some(pd) = ix.refs_of(row).first().and_then(|&r| ix.row(r))
                && self.pd_product.contains_key(&pd)
            {
                self.pds_pd.insert(row, pd);
            }
        }
    }

    fn build_representations(&mut self) {
        let ix = self.ix;
        for row in ix.rows_of(&["SHAPE_DEFINITION_REPRESENTATION"]) {
            let refs = ix.refs_of(row);
            let (Some(pds), Some(rep)) = (
                refs.first().and_then(|&r| ix.row(r)),
                refs.get(1).and_then(|&r| ix.row(r)),
            ) else {
                continue;
            };
            if let Some(pd) = self.pds_pd.get(&pds) {
                self.rep_product.insert(rep, self.pd_product[pd]);
                self.sdr_of_rep.insert(rep, row);
            }
        }
        for row in ix.rows_of(&["SHAPE_REPRESENTATION_RELATIONSHIP"]) {
            let refs = ix.refs_of(row);
            let r1 = refs.first().and_then(|&r| ix.row(r));
            let r2 = refs.get(1).and_then(|&r| ix.row(r));
            self.srr.push((row, r1, r2));
        }
        let mut changed = true;
        while changed {
            changed = false;
            for &(_, r1, r2) in &self.srr {
                let (Some(a), Some(b)) = (r1, r2) else {
                    continue;
                };
                match (
                    self.rep_product.get(&a).copied(),
                    self.rep_product.get(&b).copied(),
                ) {
                    (Some(p), None) => {
                        self.rep_product.insert(b, p);
                        changed = true;
                    }
                    (None, Some(p)) => {
                        self.rep_product.insert(a, p);
                        changed = true;
                    }
                    _ => {}
                }
            }
        }
        let mut reps: Vec<(Row, Row)> = self.rep_product.iter().map(|(&r, &p)| (r, p)).collect();
        reps.sort_unstable();
        for (rep, p) in reps {
            self.product_reps.entry(p).or_default().push(rep);
        }
    }

    fn build_assembly(&mut self) {
        let ix = self.ix;
        for row in ix.rows_of(&["NEXT_ASSEMBLY_USAGE_OCCURRENCE"]) {
            let refs = ix.refs_of(row);
            let prod = |i: usize| {
                refs.get(i)
                    .and_then(|&r| ix.row(r))
                    .and_then(|r| self.pd_product.get(&r))
                    .copied()
            };
            let occ = Occurrence {
                row,
                parent: prod(0),
                child: prod(1),
            };
            self.occurrences.push(occ);
            self.children
                .entry(occ.parent)
                .or_default()
                .push((row, occ.child));
        }
        let kids: std::collections::HashSet<Row> =
            self.occurrences.iter().filter_map(|o| o.child).collect();
        self.roots = self
            .products
            .iter()
            .copied()
            .filter(|p| {
                !kids.contains(p)
                    && (self.children.contains_key(&Some(*p)) || self.product_reps.contains_key(p))
            })
            .collect();
    }

    fn build_bodies(&mut self) {
        let ix = self.ix;
        let mut reps = ix.rows_of(&REP_TYPES);
        for row in ix.rows_of(&["CPLX"]) {
            let t = ix.text(row);
            if memchr::memmem::find(t, b"SHAPE_REPRESENTATION(").is_some()
                && memchr::memmem::find(t, b"RELATIONSHIP").is_none()
            {
                reps.push(row);
            }
        }
        reps.sort_unstable();
        reps.dedup();
        for rep in reps {
            for b in ix.refs_of(rep).iter().filter_map(|&r| ix.row(r)) {
                if self.is_body[ix.type_of(b) as usize] {
                    self.bodies.push((b, rep));
                    self.body_rep.insert(b, rep);
                }
            }
        }
    }

    fn build_styles(&mut self) {
        let ix = self.ix;
        for row in ix.rows_of(&["STYLED_ITEM", "OVER_RIDING_STYLED_ITEM"]) {
            let refs = ix.refs_of(row);
            let overriding = ix.type_name(row) == "OVER_RIDING_STYLED_ITEM";
            let (styles, target) = if overriding {
                if refs.len() < 2 {
                    continue;
                }
                (&refs[..refs.len() - 2], refs[refs.len() - 2])
            } else {
                if refs.is_empty() {
                    continue;
                }
                (&refs[..refs.len() - 1], refs[refs.len() - 1])
            };
            let target = ix.row(target);
            let style_rows: Vec<Option<Row>> = styles.iter().map(|&r| ix.row(r)).collect();
            let (surface, curve) = self.style_colours(&style_rows);
            self.styled.insert(
                row,
                Styled {
                    target,
                    surface,
                    curve,
                    overriding,
                },
            );
            if let Some(t) = target {
                self.styles_of_target.entry(t).or_default().push(row);
            }
        }
    }

    // ---- colours ---------------------------------------------------------

    fn intern_colour(&mut self, rgb: [f64; 3], name: &str) -> ColourId {
        let key = format!("{:.4},{:.4},{:.4}", rgb[0], rgb[1], rgb[2]);
        let id = match self.colour_ids.get(&key) {
            Some(&id) => id,
            None => {
                let id = self.colours.len() as ColourId;
                self.colours.push(Colour {
                    key: key.clone(),
                    rgb,
                    names: BTreeSet::new(),
                });
                self.colour_ids.insert(key, id);
                id
            }
        };
        self.colours[id as usize].names.insert(name.to_string());
        id
    }

    /// First colour reachable from `row` (depth-first in argument order, at
    /// most 8 references deep), interning it.
    fn colour_reachable(&mut self, row: Row, depth: u32) -> Option<ColourId> {
        let ix = self.ix;
        let t = ix.type_of(row);
        if t == self.t_colour || t == self.t_predef {
            if let Some(&id) = self.colour_of_row.get(&row) {
                return Some(id);
            }
            let args = ix.args(row);
            let (name, rgb) = match leading_string(args) {
                Some((raw, end)) => {
                    let name = crate::decode::decode_string(raw);
                    let rgb = if t == self.t_colour {
                        let v = numbers(&args[end..], 3);
                        [
                            v.first().copied().unwrap_or(0.0),
                            v.get(1).copied().unwrap_or(0.0),
                            v.get(2).copied().unwrap_or(0.0),
                        ]
                    } else {
                        PREDEFINED
                            .iter()
                            .find(|(n, _)| *n == name)
                            .map(|(_, c)| *c)
                            .unwrap_or([0.0; 3])
                    };
                    (name, rgb)
                }
                None => (String::new(), [0.0; 3]),
            };
            let id = self.intern_colour(rgb, &name);
            self.colour_of_row.insert(row, id);
            return Some(id);
        }
        if depth > 8 {
            return None;
        }
        for &r in ix.refs_of(row) {
            if let Some(c) = ix.row(r).and_then(|r| self.colour_reachable(r, depth + 1)) {
                return Some(c);
            }
        }
        None
    }

    /// (surface colour, curve colour) reachable from presentation style rows.
    /// Breadth-first; a two-sided face style has a `.POSITIVE.` and a
    /// `.NEGATIVE.` usage and the front (positive) side wins, as in OCCT.
    fn style_colours(
        &mut self,
        style_rows: &[Option<Row>],
    ) -> (Option<ColourId>, Option<ColourId>) {
        let ix = self.ix;
        let (mut front, mut back, mut curve) = (None, None, None);
        let mut queue: Vec<Row> = style_rows.iter().flatten().copied().collect();
        let mut seen: Vec<Row> = Vec::new();
        let mut i = 0;
        while i < queue.len() {
            let r = queue[i];
            i += 1;
            if seen.contains(&r) {
                continue;
            }
            seen.push(r);
            let t = ix.type_of(r);
            if t == self.t_surf_usage {
                let side = first_arg(ix.args(r)) == b".NEGATIVE.";
                let c = self.colour_reachable(r, 0);
                if side {
                    back = back.or(c);
                } else {
                    front = front.or(c);
                }
            } else if t == self.t_curve_style {
                curve = curve.or(self.colour_reachable(r, 0));
            } else {
                queue.extend(ix.refs_of(r).iter().filter_map(|&x| ix.row(x)));
            }
        }
        (front.or(back), curve)
    }

    /// Surface colour directly styled on `row` (first style with one).
    pub fn surface_colour(&self, row: Row) -> Option<ColourId> {
        self.styles_of_target
            .get(&row)?
            .iter()
            .find_map(|s| self.styled[s].surface)
    }

    pub fn colour_key(&self, id: ColourId) -> &str {
        &self.colours[id as usize].key
    }

    // ---- bodies -----------------------------------------------------------

    /// `(face row, owning CLOSED/OPEN_SHELL row)` for every ADVANCED_FACE of
    /// a body, by depth-first topology traversal (each face once).
    pub fn body_faces_shells(&self, body: Row) -> Vec<(Row, Option<Row>)> {
        let ix = self.ix;
        with_marks(ix.len(), |marks| {
            let mut out = Vec::new();
            let mut stack: Vec<(Row, Option<Row>)> = vec![(body, None)];
            while let Some((r, mut shell)) = stack.pop() {
                if !marks.visit(r) {
                    continue;
                }
                let t = ix.type_of(r);
                if t == self.t_face {
                    out.push((r, shell));
                } else if self.is_topo[t as usize] || t == self.t_cplx {
                    if self.is_shell[t as usize] {
                        shell = Some(r);
                    }
                    stack.extend(
                        ix.refs_of(r)
                            .iter()
                            .filter_map(|&x| ix.row(x))
                            .map(|x| (x, shell)),
                    );
                }
            }
            out
        })
    }

    pub fn body_faces(&self, body: Row) -> Vec<Row> {
        self.body_faces_shells(body)
            .into_iter()
            .map(|(f, _)| f)
            .collect()
    }

    /// Faces with several FACE_OUTER_BOUNDs are split by OCCT's ShapeFix on
    /// import; the number of extra faces that produces.
    pub fn extra_outer_bounds(&self, faces: &[Row]) -> usize {
        let ix = self.ix;
        faces
            .iter()
            .map(|&f| {
                let refs = ix.refs_of(f);
                let n = refs[..refs.len().saturating_sub(1)]
                    .iter()
                    .filter(|&&x| {
                        ix.row(x)
                            .map(|r| ix.type_of(r) == self.t_outer_bound)
                            .unwrap_or(false)
                    })
                    .count();
                n.saturating_sub(1)
            })
            .sum()
    }

    /// Coordinates of a CARTESIAN_POINT row.
    pub fn point(&self, row: Row) -> [f64; 3] {
        let args = self.ix.args(row);
        let from = memchr::memchr(b'(', args).unwrap_or(0);
        let v = numbers(&args[from..], 3);
        [
            v.first().copied().unwrap_or(0.0),
            v.get(1).copied().unwrap_or(0.0),
            v.get(2).copied().unwrap_or(0.0),
        ]
    }

    /// Bounding box of all vertex points reachable from a body.
    pub fn body_bbox(&self, body: Row) -> Option<BBox> {
        let ix = self.ix;
        with_marks(ix.len(), |marks| {
            let mut stack = vec![body];
            let mut bb = BBox {
                min: [f64::INFINITY; 3],
                max: [f64::NEG_INFINITY; 3],
                vertices: 0,
            };
            while let Some(r) = stack.pop() {
                if !marks.visit(r) {
                    continue;
                }
                let t = ix.type_of(r);
                if t == self.t_face {
                    let refs = ix.refs_of(r);
                    stack.extend(
                        refs[..refs.len().saturating_sub(1)]
                            .iter()
                            .filter_map(|&x| ix.row(x)),
                    );
                } else if t == self.t_vertex {
                    for p in ix.refs_of(r).iter().filter_map(|&x| ix.row(x)) {
                        if ix.type_of(p) == self.t_point {
                            let c = self.point(p);
                            for (k, v) in c.iter().enumerate() {
                                bb.min[k] = bb.min[k].min(*v);
                                bb.max[k] = bb.max[k].max(*v);
                            }
                            bb.vertices += 1;
                        }
                    }
                } else if self.is_topo[t as usize] || t == self.t_cplx {
                    stack.extend(ix.refs_of(r).iter().filter_map(|&x| ix.row(x)));
                }
            }
            (bb.vertices > 0).then_some(bb)
        })
    }

    /// Effective colour of every face of a body: face style, else the style
    /// of its shell, else the body style. `None` is uncoloured.
    pub fn face_colour_hist(&self, body: Row) -> HashMap<Option<ColourId>, usize> {
        let bc = self.surface_colour(body);
        let mut hist = HashMap::new();
        for (f, shell) in self.body_faces_shells(body) {
            let c = self
                .surface_colour(f)
                .or_else(|| shell.and_then(|s| self.surface_colour(s)))
                .or(bc);
            *hist.entry(c).or_insert(0) += 1;
        }
        hist
    }

    pub fn body_product(&self, body: Row) -> Option<Row> {
        self.body_rep
            .get(&body)
            .and_then(|r| self.rep_product.get(r))
            .copied()
    }

    pub fn product_name(&self, p: Row) -> &str {
        self.product_name.get(&p).map(|s| s.as_str()).unwrap_or("?")
    }
}
