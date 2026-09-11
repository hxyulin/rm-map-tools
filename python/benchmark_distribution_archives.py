#!/usr/bin/env python3
"""Measure tar.zst size and speed and verify every archived file by SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time


def checksum(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--glob', default='*.step')
    ap.add_argument('--levels', type=int, nargs='+', default=[3, 9, 15])
    args = ap.parse_args()
    files = sorted(args.source.glob(args.glob))
    if not files or any(not p.is_file() for p in files):
        ap.error('glob must select regular files')
    args.output.mkdir(parents=True, exist_ok=False)
    expected = {}
    tarpath = args.output/'bundle.tar'
    with tarfile.open(tarpath, 'w', format=tarfile.USTAR_FORMAT) as tar:
        for path in files:
            with path.open('rb') as f:
                expected[path.name] = checksum(f)
            info = tar.gettarinfo(str(path), arcname=path.name)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ''
            info.mode = 0o644
            with path.open('rb') as f:
                tar.addfile(info, f)
    report = dict(source=str(args.source.resolve()), glob=args.glob,
                  files=expected, source_bytes=sum(p.stat().st_size for p in files),
                  tar_bytes=tarpath.stat().st_size,
                  zstd_version=subprocess.check_output(['zstd','--version'],text=True).strip(), results=[])
    for level in args.levels:
        archive = args.output/f'bundle-{level}.tar.zst'
        start = time.perf_counter()
        subprocess.run(['zstd',f'-{level}','-T1','--no-progress',str(tarpath),'-o',str(archive)],check=True)
        compress_seconds = time.perf_counter()-start
        start = time.perf_counter()
        process = subprocess.Popen(['zstd','-dc',str(archive)],stdout=subprocess.PIPE)
        found = {}
        try:
            with tarfile.open(fileobj=process.stdout,mode='r|') as tar:
                for member in tar:
                    if not member.isfile() or member.name in found:
                        raise ValueError('unexpected or duplicate archive member')
                    with tar.extractfile(member) as f:
                        found[member.name]=checksum(f)
            # Drain remaining tar padding so the decompressor completes normally.
            while process.stdout.read(1024 * 1024):
                pass
        finally:
            process.stdout.close()
        if process.wait() != 0 or found != expected:
            raise ValueError('archive roundtrip failed')
        row=dict(level=level,bytes=archive.stat().st_size,compress_seconds=compress_seconds,
                 decompress_and_verify_seconds=time.perf_counter()-start,verified_files=len(found))
        report['results'].append(row)
        print(json.dumps(row),flush=True)
        (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    tarpath.unlink()

if __name__ == '__main__': main()
