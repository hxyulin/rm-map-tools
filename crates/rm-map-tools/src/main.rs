//! `rm-map-tools`: index, inspect and (later) split the DJI RMUC STEP files.

use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use rayon::prelude::*;
use serde::Serialize;
use step21::Index;
use step21::model::{ColourId, Model};
use step21::split::{Scratch, Splitter, part_filename};

#[derive(Parser)]
#[command(version, about)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// One streaming pass over a STEP file; writes the sidecar index (`<file>.p21idx` by default).
    Index {
        step: PathBuf,
        #[arg(short, long)]
        out: Option<PathBuf>,
    },
    /// Products, assembly tree, bodies, faces and colour summary of a STEP file.
    Inspect {
        /// STEP file, or a sidecar index written by `index`.
        step: PathBuf,
        /// Write the full summary as JSON to this file.
        #[arg(long)]
        json: Option<PathBuf>,
        /// Depth of the assembly tree to print.
        #[arg(long, default_value_t = 2)]
        depth: usize,
        /// Print the per-type entity histogram.
        #[arg(long)]
        types: bool,
    },
    /// Split a STEP file into one standalone STEP file per product (lossless, text level).
    Split {
        /// STEP file, or a sidecar index written by `index`.
        step: PathBuf,
        /// Output package directory (`parts/*.stp` and `parts.json`).
        #[arg(short, long)]
        out: PathBuf,
        /// Only these product names (comma separated).
        #[arg(long)]
        products: Option<String>,
        /// Stop after N products.
        #[arg(long, default_value_t = 0)]
        limit: usize,
        /// Worker threads (default: all cores).
        #[arg(short, long)]
        jobs: Option<usize>,
    },
}

fn main() -> Result<()> {
    match Cli::parse().cmd {
        Cmd::Index { step, out } => {
            let t = Instant::now();
            let ix = Index::build(&step).with_context(|| format!("indexing {}", step.display()))?;
            let built = t.elapsed();
            let out = out.unwrap_or_else(|| sidecar_path(&step));
            ix.save(&out)
                .with_context(|| format!("writing {}", out.display()))?;
            eprintln!(
                "{}: {} entities, {} refs, {} types, scan {:.2}s, save {:.2}s -> {}",
                step.display(),
                ix.len(),
                ix.ref_count(),
                ix.type_names().len(),
                built.as_secs_f64(),
                (t.elapsed() - built).as_secs_f64(),
                out.display()
            );
        }
        Cmd::Inspect {
            step,
            json,
            depth,
            types,
        } => {
            let t = Instant::now();
            let ix = open_index(&step)?;
            let t_index = t.elapsed();
            let t = Instant::now();
            let m = Model::new(&ix);
            let t_model = t.elapsed();
            let t = Instant::now();
            let s = summarise(&ix, &m);
            let t_bodies = t.elapsed();
            print_summary(&ix, &m, &s, depth);
            if types {
                for (name, n) in ix.type_histogram() {
                    println!("{n:>10}  {name}");
                }
            }
            eprintln!(
                "timing: index {:.2}s, model {:.2}s, bodies {:.2}s, peak rss {} MB",
                t_index.as_secs_f64(),
                t_model.as_secs_f64(),
                t_bodies.as_secs_f64(),
                peak_rss_mb()
            );
            if let Some(path) = json {
                std::fs::write(&path, serde_json::to_string_pretty(&s)?)
                    .with_context(|| format!("writing {}", path.display()))?;
            }
        }
        Cmd::Split {
            step,
            out,
            products,
            limit,
            jobs,
        } => {
            if let Some(j) = jobs {
                rayon::ThreadPoolBuilder::new()
                    .num_threads(j)
                    .build_global()?;
            }
            let t = Instant::now();
            let ix = open_index(&step)?;
            let t_index = t.elapsed();
            let t = Instant::now();
            let m = Model::new(&ix);
            let t_model = t.elapsed();
            let sp = Splitter::new(&ix, &m);
            eprintln!(
                "index {:.2}s, model {:.2}s, reverse tables {:.2}s",
                t_index.as_secs_f64(),
                t_model.as_secs_f64(),
                t.elapsed().as_secs_f64() - t_model.as_secs_f64()
            );
            let mut prods = sp.products();
            if let Some(names) = products {
                let want: Vec<&str> = names.split(',').collect();
                prods.retain(|p| want.contains(&m.product_name(*p)));
            }
            if limit > 0 {
                prods.truncate(limit);
            }
            split_package(&ix, &m, &sp, &prods, &out)?;
        }
    }
    Ok(())
}

#[derive(Serialize)]
struct BodyEntry {
    id: u32,
    #[serde(rename = "type")]
    kind: String,
    faces: usize,
    extra_outer_bounds: usize,
    body_colour: Option<String>,
    face_colours: HashMap<String, usize>,
    bbox_min: Option<[f64; 3]>,
    bbox_max: Option<[f64; 3]>,
    vertices: usize,
}

#[derive(Serialize)]
struct PartEntry {
    file: String,
    product_id: u32,
    name: String,
    entities: usize,
    rewritten: usize,
    bytes: u64,
    bodies: Vec<BodyEntry>,
    seconds: f64,
}

#[derive(Serialize)]
struct Manifest {
    source: String,
    source_size: u64,
    entities: usize,
    parts: Vec<PartEntry>,
    colour_names: std::collections::BTreeMap<String, Vec<String>>,
    total_entities_written: usize,
    total_bytes_written: u64,
    split_seconds: f64,
}

fn round4(v: [f64; 3]) -> [f64; 3] {
    v.map(|x| (x * 1e4).round_ties_even() / 1e4)
}

fn body_entries(ix: &Index, m: &Model, product: u32) -> Vec<BodyEntry> {
    m.bodies
        .iter()
        .filter(|(_, rep)| m.rep_product.get(rep) == Some(&product))
        .map(|&(b, _)| {
            let faces = m.body_faces(b);
            let bb = m.body_bbox(b);
            let face_colours = m
                .face_colour_hist(b)
                .into_iter()
                .map(|(c, n)| {
                    (
                        c.map(|c| m.colour_key(c).to_string())
                            .unwrap_or_else(|| "None".into()),
                        n,
                    )
                })
                .collect();
            BodyEntry {
                id: ix.id(b),
                kind: ix.type_name(b).to_string(),
                faces: faces.len(),
                extra_outer_bounds: m.extra_outer_bounds(&faces),
                body_colour: m.surface_colour(b).map(|c| m.colour_key(c).to_string()),
                face_colours,
                bbox_min: bb.map(|b| round4(b.min)),
                bbox_max: bb.map(|b| round4(b.max)),
                vertices: bb.map(|b| b.vertices).unwrap_or(0),
            }
        })
        .collect()
}

fn split_package(ix: &Index, m: &Model, sp: &Splitter, prods: &[u32], out: &Path) -> Result<()> {
    let parts_dir = out.join("parts");
    std::fs::create_dir_all(&parts_dir)
        .with_context(|| format!("creating {}", parts_dir.display()))?;
    let t = Instant::now();
    let done = std::sync::atomic::AtomicUsize::new(0);
    let entries: Vec<PartEntry> = prods
        .par_iter()
        .map_init(
            || Scratch::new(ix),
            |scratch, &p| -> Result<PartEntry> {
                let ts = Instant::now();
                let pid = ix.id(p);
                let name = m.product_name(p).to_string();
                let fn_ = part_filename(&name, pid);
                let closure = sp.closure(p, scratch);
                let path = parts_dir.join(&fn_);
                let mut w =
                    std::io::BufWriter::with_capacity(1 << 20, std::fs::File::create(&path)?);
                let bytes = sp
                    .write_part(&closure, &mut w)
                    .with_context(|| format!("writing {}", path.display()))?;
                w.flush()?;
                let bodies = body_entries(ix, m, p);
                let n = done.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
                if n.is_multiple_of(100) || n == prods.len() {
                    eprintln!(
                        "[{n}/{}] {fn_}: {} entities, {:.1} MB, {} bodies",
                        prods.len(),
                        closure.rows.len(),
                        bytes as f64 / 1e6,
                        bodies.len()
                    );
                }
                Ok(PartEntry {
                    file: format!("parts/{fn_}"),
                    product_id: pid,
                    name,
                    entities: closure.rows.len(),
                    rewritten: closure.rewritten.len(),
                    bytes,
                    bodies,
                    seconds: ts.elapsed().as_secs_f64(),
                })
            },
        )
        .collect::<Result<_>>()?;
    let total_entities: usize = entries.iter().map(|e| e.entities).sum();
    let total_bytes: u64 = entries.iter().map(|e| e.bytes).sum();
    let manifest = Manifest {
        source: ix.source().display().to_string(),
        source_size: ix.data().len() as u64,
        entities: ix.len(),
        parts: entries,
        colour_names: m
            .colours
            .iter()
            .map(|c| (c.key.clone(), c.names.iter().cloned().collect()))
            .collect(),
        total_entities_written: total_entities,
        total_bytes_written: total_bytes,
        split_seconds: t.elapsed().as_secs_f64(),
    };
    let mpath = out.join("parts.json");
    std::fs::write(&mpath, serde_json::to_string_pretty(&manifest)?)
        .with_context(|| format!("writing {}", mpath.display()))?;
    eprintln!(
        "{} parts, {} entities ({:.2}x source), {:.0} MB, {:.1}s, peak rss {} MB",
        prods.len(),
        total_entities,
        total_entities as f64 / ix.len() as f64,
        total_bytes as f64 / 1e6,
        t.elapsed().as_secs_f64(),
        peak_rss_mb()
    );
    Ok(())
}

fn sidecar_path(step: &Path) -> PathBuf {
    let mut s = step.as_os_str().to_owned();
    s.push(".p21idx");
    PathBuf::from(s)
}

/// Open a STEP file (building the index in memory, or loading a fresh
/// sidecar next to it) or a sidecar index directly.
fn open_index(path: &Path) -> Result<Index> {
    if path.extension().is_some_and(|e| e == "p21idx") {
        return Index::load(path).with_context(|| format!("loading {}", path.display()));
    }
    let side = sidecar_path(path);
    if side.exists() {
        match Index::load(&side) {
            Ok(ix) => return Ok(ix),
            Err(e) => eprintln!("ignoring sidecar {}: {e}", side.display()),
        }
    }
    Index::build(path).with_context(|| format!("indexing {}", path.display()))
}

#[derive(Serialize)]
struct Summary {
    source: String,
    bytes: u64,
    entities: usize,
    refs: usize,
    types: usize,
    max_id: u32,
    products: usize,
    occurrences: usize,
    roots: Vec<String>,
    bodies: usize,
    bodies_by_type: Vec<(String, usize)>,
    bodies_without_product: usize,
    faces: usize,
    vertices: usize,
    bbox_min: Option<[f64; 3]>,
    bbox_max: Option<[f64; 3]>,
    styled: usize,
    style_targets: Vec<(String, usize)>,
    colours: usize,
    /// Colour key -> names given in the file.
    colour_names: Vec<(String, Vec<String>)>,
    /// Effective face colour histogram over all bodies, most frequent first ("null" = uncoloured).
    face_colours: Vec<(String, usize)>,
}

fn summarise(ix: &Index, m: &Model) -> Summary {
    let mut by_type: HashMap<&str, usize> = HashMap::new();
    let mut faces = 0;
    let mut vertices = 0;
    let mut bbox: Option<([f64; 3], [f64; 3])> = None;
    let mut hist: HashMap<Option<ColourId>, usize> = HashMap::new();
    let mut without_product = 0;
    for &(body, _) in &m.bodies {
        *by_type.entry(ix.type_name(body)).or_default() += 1;
        for (c, n) in m.face_colour_hist(body) {
            *hist.entry(c).or_default() += n;
            faces += n;
        }
        if let Some(bb) = m.body_bbox(body) {
            vertices += bb.vertices;
            let (mn, mx) = bbox.get_or_insert((bb.min, bb.max));
            for k in 0..3 {
                mn[k] = mn[k].min(bb.min[k]);
                mx[k] = mx[k].max(bb.max[k]);
            }
        }
        if m.body_product(body).is_none() {
            without_product += 1;
        }
    }
    let mut targets: HashMap<&str, usize> = HashMap::new();
    for s in m.styled.values() {
        *targets
            .entry(s.target.map(|t| ix.type_name(t)).unwrap_or("?"))
            .or_default() += 1;
    }
    let mut face_colours: Vec<(String, usize)> = hist
        .into_iter()
        .map(|(c, n)| {
            (
                c.map(|c| m.colour_key(c).to_string())
                    .unwrap_or_else(|| "null".into()),
                n,
            )
        })
        .collect();
    face_colours.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    let sorted = |h: HashMap<&str, usize>| {
        let mut v: Vec<(String, usize)> = h.into_iter().map(|(k, n)| (k.to_string(), n)).collect();
        v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        v
    };
    let mut colour_names: Vec<(String, Vec<String>)> = m
        .colours
        .iter()
        .map(|c| (c.key.clone(), c.names.iter().cloned().collect()))
        .collect();
    colour_names.sort();
    Summary {
        source: ix.source().display().to_string(),
        bytes: ix.data().len() as u64,
        entities: ix.len(),
        refs: ix.ref_count(),
        types: ix.type_names().len(),
        max_id: ix.max_id(),
        products: m.products.len(),
        occurrences: m.occurrences.len(),
        roots: m
            .roots
            .iter()
            .map(|&r| m.product_name(r).to_string())
            .collect(),
        bodies: m.bodies.len(),
        bodies_by_type: sorted(by_type),
        bodies_without_product: without_product,
        faces,
        vertices,
        bbox_min: bbox.map(|b| b.0),
        bbox_max: bbox.map(|b| b.1),
        styled: m.styled.len(),
        style_targets: sorted(targets),
        colours: m.colours.len(),
        colour_names,
        face_colours,
    }
}

fn print_summary(ix: &Index, m: &Model, s: &Summary, depth: usize) {
    println!("{}  ({:.1} MB)", s.source, s.bytes as f64 / 1e6);
    println!(
        "entities {}  refs {}  types {}  max id {}",
        s.entities, s.refs, s.types, s.max_id
    );
    println!(
        "products {}  occurrences {}  roots {:?}",
        s.products, s.occurrences, s.roots
    );
    let bt: Vec<String> = s
        .bodies_by_type
        .iter()
        .map(|(t, n)| format!("{n} {t}"))
        .collect();
    println!(
        "bodies {} ({})  without product {}",
        s.bodies,
        bt.join(", "),
        s.bodies_without_product
    );
    println!("faces {}  vertices {}", s.faces, s.vertices);
    if let (Some(mn), Some(mx)) = (s.bbox_min, s.bbox_max) {
        println!(
            "bbox min {:.1} {:.1} {:.1}  max {:.1} {:.1} {:.1}  (mm, {:.2} x {:.2} x {:.2} m)",
            mn[0],
            mn[1],
            mn[2],
            mx[0],
            mx[1],
            mx[2],
            (mx[0] - mn[0]) / 1e3,
            (mx[1] - mn[1]) / 1e3,
            (mx[2] - mn[2]) / 1e3
        );
    }
    let st: Vec<String> = s
        .style_targets
        .iter()
        .map(|(t, n)| format!("{n} {t}"))
        .collect();
    println!("styled items {} on {}", s.styled, st.join(", "));
    println!("colours {} distinct; effective face colours:", s.colours);
    let names: HashMap<&str, &Vec<String>> = s
        .colour_names
        .iter()
        .map(|(k, v)| (k.as_str(), v))
        .collect();
    for (key, n) in s.face_colours.iter().take(16) {
        let nm = names
            .get(key.as_str())
            .map(|v| v.join("|"))
            .unwrap_or_default();
        println!("  {n:>8}  {key:<24} {nm}");
    }
    if s.face_colours.len() > 16 {
        println!("  ... {} more", s.face_colours.len() - 16);
    }
    // assembly tree
    let mut bodies_of: HashMap<Option<u32>, usize> = HashMap::new();
    for &(b, _) in &m.bodies {
        *bodies_of.entry(m.body_product(b)).or_default() += 1;
    }
    println!("assembly tree (depth {depth}):");
    for &root in &m.roots {
        println!("  {}", m.product_name(root));
        print_tree(ix, m, &bodies_of, root, 2, depth);
    }
}

fn print_tree(
    ix: &Index,
    m: &Model,
    bodies_of: &HashMap<Option<u32>, usize>,
    p: u32,
    indent: usize,
    depth: usize,
) {
    let Some(kids) = m.children.get(&Some(p)) else {
        return;
    };
    let mut count: Vec<(Option<u32>, usize)> = Vec::new();
    for &(_, c) in kids {
        match count.iter_mut().find(|(k, _)| *k == c) {
            Some(e) => e.1 += 1,
            None => count.push((c, 1)),
        }
    }
    let shown = if count.len() > 12 { 8 } else { count.len() };
    for (c, n) in &count[..shown] {
        let (c, n) = (*c, *n);
        let name = c.map(|c| m.product_name(c)).unwrap_or("?");
        let sub = c
            .and_then(|c| m.children.get(&Some(c)))
            .map(|v| v.len())
            .unwrap_or(0);
        let bodies = bodies_of.get(&c).copied().unwrap_or(0);
        let id = c.map(|c| ix.id(c)).unwrap_or(0);
        println!(
            "{:indent$}{name} x{n}  (#{id}, {sub} children, {bodies} bodies)",
            "",
            indent = indent
        );
        if indent / 2 < depth
            && let Some(c) = c
        {
            print_tree(ix, m, bodies_of, c, indent + 2, depth);
        }
    }
    if shown < count.len() {
        let rest = &count[shown..];
        let occ: usize = rest.iter().map(|(_, n)| n).sum();
        let bodies: usize = rest
            .iter()
            .map(|(c, _)| bodies_of.get(c).copied().unwrap_or(0))
            .sum();
        println!(
            "{:indent$}... {} more distinct children ({occ} occurrences, {bodies} bodies)",
            "",
            rest.len(),
            indent = indent
        );
    }
}

fn peak_rss_mb() -> u64 {
    #[cfg(unix)]
    {
        // `ru_maxrss` is bytes on macOS and kilobytes on Linux.
        let out = std::process::Command::new("ps")
            .args(["-o", "rss=", "-p", &std::process::id().to_string()])
            .output();
        if let Ok(o) = out
            && let Ok(kb) = String::from_utf8_lossy(&o.stdout).trim().parse::<u64>()
        {
            return kb / 1024;
        }
    }
    0
}
