#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure STEP package parsing, layer list reuse and streamed ZIP storage.

Run on package directories, each containing field.step. Archives are measured
with identical ZIP/DEFLATE level 6 settings, then discarded. No CAD is rewritten.
Single-run wall times are indicative, not a controlled performance benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import zipfile

import numpy as np
from cad_share_values import profile, native_summary
from p21index import Index


def layers(ix):
    """Intern exact ordered membership arrays for accounting, never rewrite layers."""
    groups = {}; total = 0; unique = 0; aliases = 0
    for row in ix.rows_of('PRESENTATION_LAYER_ASSIGNMENT'):
        refs = ix.refs_of(int(row)); total += len(refs)
        key = refs.tobytes()
        if key in groups:
            aliases += 1
        else:
            groups[key] = True; unique += len(refs)
    return {'records': len(groups) + aliases, 'unique_ordered_membership_lists': len(groups),
            'references': total, 'interned_references': unique,
            'reference_array_bytes': total * ix.refs.dtype.itemsize,
            'interned_reference_array_bytes': unique * ix.refs.dtype.itemsize,
            'scope': 'array storage only; excludes dictionary/index/object overhead; no layer names or bindings removed'}


def measure(package, *, native=False, archive_out=None):
    package = Path(package).resolve(); step = package / 'field.step'
    start = time.perf_counter()
    with Index.from_step(step, workers=1) as ix:
        seconds = time.perf_counter() - start
        report = {'path': str(package), **profile(ix),
                  'sha256': hashlib.sha256(ix.mm).hexdigest(),
                  'serial_index_seconds': seconds, 'layers': layers(ix)}
    files = sorted(p for p in package.rglob('*') if p.is_file())
    report['package_bytes'] = sum(p.stat().st_size for p in files)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'package.zip'; start = time.perf_counter()
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for path in files:
                with path.open('rb') as source, zipped.open(path.relative_to(package).as_posix(), 'w', force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=1024*1024)
        report['zip_seconds'] = time.perf_counter() - start
        report['zip_bytes'] = archive.stat().st_size
        with zipfile.ZipFile(archive) as zipped:
            report['zip_entries'] = {i.filename: {'bytes': i.file_size, 'deflated_bytes': i.compress_size} for i in zipped.infolist()}
        if archive_out is not None:
            archive_out = Path(archive_out)
            archive_out.mkdir(parents=True, exist_ok=True)
            target = archive_out / (package.name + '.zip')
            with target.open('xb') as output, archive.open('rb') as source:
                shutil.copyfileobj(source, output, length=1024*1024)
    if native:
        start = time.perf_counter(); report['native'] = native_summary(step)
        report['native_read_seconds'] = time.perf_counter() - start
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native', action='store_true', help='also compare geometry/names-only native reads')
    parser.add_argument('--archive-out', type=Path, help='optionally retain measured archives in a new directory')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    if args.archive_out is not None and args.archive_out.exists():
        raise FileExistsError(args.archive_out)
    if len({p.name for p in args.packages}) != len(args.packages):
        raise ValueError('package names must be distinct')
    report = {'schema_version': 1, 'zip_compression': 'ZIP DEFLATE level 6, identical settings; includes all package files',
              'timing_scope': 'one serial run per input; warm cache and machine load affect times',
              'packages': []}
    for package in args.packages:
        result = measure(package, native=args.native, archive_out=args.archive_out); report['packages'].append(result)
        print(package, result['bytes'], result['zip_bytes'], result['serial_index_seconds'], flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
