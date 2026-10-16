#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Stream reproducible CAD packages to tar.zst with checksum/SHA-256 read-back.

Level 22 is the release default; compression is an offline operation. No
uncompressed tar or entire CAD payload is held in memory. No archive is
published by this module. Original source files must be immutable during use.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import time

import zstandard as zstd


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package_files(package):
    """Return stable relative names for regular files; reject symlinks/devices."""
    package = Path(package).resolve()
    if not package.is_dir():
        raise ValueError('package must be a directory')
    files = {}
    for path in sorted(package.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('only regular package files/directories are supported')
        if path.is_file():
            files[path.relative_to(package).as_posix()] = path
    if not files:
        raise ValueError('package is empty')
    return files


def verify_archive(archive, expected):
    """Stream every member through SHA-256 and consume the frame checksum."""
    observed = set(); start = time.perf_counter()
    with Path(archive).open('rb') as compressed:
        with zstd.ZstdDecompressor().stream_reader(compressed) as stream:
            with tarfile.open(fileobj=stream, mode='r|') as tar:
                for member in tar:
                    if not member.isfile() or member.name in observed or member.name not in expected:
                        raise ValueError('unexpected/duplicate archive member')
                    observed.add(member.name)
                    with tar.extractfile(member) as source:
                        if hashlib.file_digest(source, 'sha256').hexdigest() != expected[member.name]:
                            raise ValueError(f'archive content mismatch: {member.name}')
            # tar iteration ends before frame/padding EOF. Consume all remaining
            # bytes so a truncated/corrupt frame checksum cannot escape checking.
            while stream.read(1024 * 1024):
                pass
    if observed != expected.keys():
        raise ValueError('missing archive members')
    # stream_reader can return EOF for a frame missing only its checksum bytes.
    # Check the decoder's explicit eof flag as well; tar's end markers cannot
    # prove Zstandard frame completeness. A second streamed pass is inexpensive
    # compared with offline compression and rejects appended frames/data too.
    with Path(archive).open('rb') as compressed:
        decoder = zstd.ZstdDecompressor().decompressobj()
        while chunk := compressed.read(16384):
            decoder.decompress(chunk)
            if decoder.eof:
                if decoder.unused_data or compressed.read(1):
                    raise ValueError('trailing Zstandard frame/data')
                break
        if not decoder.eof:
            raise ValueError('incomplete Zstandard frame')
    return time.perf_counter() - start


def create_archive(package, destination, *, level=22, include=None, extra_files=None, prefix=''):
    """Create a new normalized tar.zst atomically after complete read-back."""
    if not 1 <= level <= zstd.MAX_COMPRESSION_LEVEL:
        raise ValueError('compression level must be between 1 and 22')
    package = Path(package).resolve(); destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    if destination.is_relative_to(package):
        raise ValueError('archive must be outside the input package')
    files = package_files(package)
    if include is not None:
        files = {name: files[name] for name in include}
    for name, path in (extra_files or {}).items():
        if name in files:
            raise ValueError('duplicate archive name')
        path = Path(path)
        if not path.is_file() or path.is_symlink():
            raise ValueError('extra archive sources must be regular files')
        files[name] = path
    files = {(prefix + '/' if prefix else '') + name: path for name, path in files.items()}
    for name in files:
        if name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/')) or '\\' in name:
            raise ValueError('unsafe archive member name')
    files = dict(sorted(files.items()))
    expected = {name: file_digest(path) for name, path in files.items()}
    source_bytes = sum(path.stat().st_size for path in files.values())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        archive = Path(tmp) / 'package.tar.zst'
        compressor = zstd.ZstdCompressor(level=level, threads=0, write_checksum=True)
        start = time.perf_counter()
        with archive.open('wb') as output:
            with compressor.stream_writer(output) as stream:
                with tarfile.open(fileobj=stream, mode='w|', format=tarfile.PAX_FORMAT) as tar:
                    for name, path in files.items():
                        info = tarfile.TarInfo(name)
                        info.size = path.stat().st_size; info.mode = 0o644
                        # TarInfo defaults uid/gid/mtime to zero and names to ''.
                        with path.open('rb') as source:
                            tar.addfile(info, source)
        compression_seconds = time.perf_counter() - start
        with archive.open('rb') as stream:
            frame = zstd.get_frame_parameters(stream.read(18))
        verification_seconds = verify_archive(archive, expected)
        if any(file_digest(path) != expected[name] for name, path in files.items()):
            raise ValueError('package source changed while archiving')
        report = {'format': 'tar.zst', 'level': level, 'threads': 0,
                  'zstandard_python_version': zstd.__version__,
                  'zstd_library_version': list(zstd.ZSTD_VERSION),
                  'source_bytes': source_bytes, 'archive_bytes': archive.stat().st_size,
                  'archive_sha256': file_digest(archive),
                  'compression_seconds': compression_seconds,
                  'decompression_and_sha256_seconds': verification_seconds,
                  'window_bytes': frame.window_size,
                  'frame_checksum': frame.has_checksum,
                  'compressor_context_bytes': compressor.memory_size(),
                  'all_member_sha256_verified': True, 'files_sha256': expected}
        # Same-filesystem hard link publishes atomically and refuses a target
        # created during a long compression run; rename would overwrite it.
        os.link(archive, destination)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--out', type=Path, required=True, help='new output directory')
    parser.add_argument('--levels', nargs='+', type=int, default=[3, 22])
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    if len(set(args.levels)) != len(args.levels):
        raise ValueError('duplicate compression levels')
    if any(level < 1 or level > zstd.MAX_COMPRESSION_LEVEL for level in args.levels):
        parser.error('levels must be between 1 and 22')
    args.out.mkdir(parents=True)
    results = []
    for level in args.levels:
        result = create_archive(args.package, args.out / f'{args.package.name}-zstd{level}.tar.zst', level=level)
        results.append(result)
        print(json.dumps(result), flush=True)
        (args.out / 'compression.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
