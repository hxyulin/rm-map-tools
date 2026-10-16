#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Repack a pinned stage-one ZIP as tar.zst, preserving all six payload files.

Original release.json bytes and tool provenance remain unchanged. Standalone
repack.json records the transport change; SHA256SUMS covers the new assets.
Nothing is uploaded or published by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from cad_archive import create_archive, file_digest

PAYLOAD = ('field.step', 'hierarchy.json', 'native-validation.json', 'NOTICE.md', 'release.json', 'README.txt')


def repack(source, out, tag, expected_sha256, *, level=22):
    """Refuse existing outputs; retain byte-identical payload and verify new archive."""
    source, out = Path(source).resolve(), Path(out).resolve()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', tag):
        raise ValueError('unsafe release tag')
    if out.exists():
        raise FileExistsError(out)
    if file_digest(source) != expected_sha256:
        raise ValueError('source ZIP SHA-256 mismatch')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        payload = Path(tmp) / 'payload'; payload.mkdir()
        stage = Path(tmp) / 'release'; stage.mkdir()
        with zipfile.ZipFile(source) as zipped:
            names = [tag + '/' + name for name in PAYLOAD]
            if len(zipped.infolist()) != len(names) or set(zipped.namelist()) != set(names):
                raise ValueError('unexpected or duplicate ZIP payload')
            for name in PAYLOAD:
                with zipped.open(tag + '/' + name) as src, (payload / name).open('xb') as dst:
                    shutil.copyfileobj(src, dst, length=1024*1024)
        original = json.loads((payload / 'release.json').read_text())
        if original.get('release_tag') != tag or set(original['files_sha256']) != set(PAYLOAD[:4]):
            raise ValueError('release provenance does not match ZIP payload')
        for name, expected in original['files_sha256'].items():
            if file_digest(payload / name) != expected:
                raise ValueError('original file checksum mismatch')
        archive = stage / (tag + '.tar.zst')
        report = create_archive(payload, archive, level=level, prefix=tag)
        report.update(schema_version=1, operation='transport-only-repack',
                      original_zip_sha256=expected_sha256,
                      original_zip_bytes=source.stat().st_size,
                      original_tool_commit=original['tool_commit'],
                      all_six_original_payload_files_byte_identical=True,
                      producer_sha256={str(path.relative_to(ROOT)): file_digest(path)
                                       for path in (Path(__file__).resolve(), ROOT/'python/cad_archive.py')})
        if file_digest(source) != expected_sha256:
            raise ValueError('source ZIP changed while repacking')
        shutil.copyfile(payload / 'release.json', stage / 'release.json')
        (stage / 'repack.json').write_text(json.dumps(report, indent=2) + '\n')
        (stage / 'SHA256SUMS').write_text(''.join(f'{file_digest(stage/name)}  {name}\n'
                                              for name in (archive.name, 'release.json', 'repack.json')))
        stage.rename(out)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_zip', type=Path)
    parser.add_argument('--source-zip-sha256', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--zstd-level', type=int, default=22)
    args = parser.parse_args()
    report = repack(args.source_zip, args.out, args.tag, args.source_zip_sha256, level=args.zstd_level)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
