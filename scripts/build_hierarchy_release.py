#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build, validate and package stage-one source CAD; publishing is a separate action.

Run with the OCP Python environment from a clean, committed source checkout.
The optional baseline verifies the freshly generated geometry and hierarchy
against a previously reviewed package. Original CAD is not included in archives.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=('field.step','hierarchy.json','native-validation.json','NOTICE.md')


def digest(path):
    """Stream a file's SHA-256 without keeping the CAD file in memory."""
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def validate_package(package, source_sha256, baseline=None):
    """Verify preservation claims, native coverage and every recorded file hash."""
    package=Path(package)
    report=json.loads((package/'hierarchy.json').read_text())
    native=json.loads((package/'native-validation.json').read_text())
    if report['source_sha256']!=source_sha256:
        raise ValueError('package/source SHA-256 mismatch')
    for key in ('source_geometry_preserved','assembly_graph_verified','source_world_placements_verified'):
        if report.get(key) is not True:raise ValueError(f'missing preservation check: {key}')
    if native.get('single_root_assembly') is not True or native['native_faces']!=report['expected_placed_faces']:
        raise ValueError('native face coverage mismatch')
    if not {'field.step','NOTICE.md'}<=report['files_sha256'].keys():
        raise ValueError('missing package checksums')
    for name,expected in report['files_sha256'].items():
        if name not in FILES or digest(package/name)!=expected:raise ValueError(f'package checksum mismatch: {name}')
    if baseline is not None:
        original=json.loads((Path(baseline)/'hierarchy.json').read_text())
        for key in ('source_sha256','geometry_record_sha256','source_face_definitions','expected_placed_faces',
                    'source_body_definitions','source_placed_bodies','source_product_occurrences',
                    'work_part_definitions','components','assemblies','source_occurrences','source_product_definitions'):
            if report[key]!=original[key]:raise ValueError(f'reviewed baseline differs: {key}')
    return report,native


def package_release(package, out, tag, manifest):
    """Atomically write a ZIP, standalone provenance and checksums; read it back."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*',tag):raise ValueError('unsafe release tag')
    package,out=Path(package),Path(out)
    if out.exists():raise ValueError('release output exists')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as temporary:
        stage=Path(temporary)/'release';stage.mkdir()
        manifest={**manifest,'release_tag':tag,'files_sha256':{name:digest(package/name) for name in FILES}}
        (stage/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
        readme=stage/'README.txt'
        readme.write_text(f'''RMUC 2027 stage-one hierarchical source CAD

Open field.step in a CAD editor. Coordinates: original source frame, mm, Z up.
Original analytic geometry and styles are retained; this is not a runtime mesh
package or a completed mechanical articulation model. See hierarchy.json for
work parts, shared definitions, source identities, placements and validation.

Tool source commit: {manifest.get('tool_commit','see release.json')}
Source CAD SHA-256: {manifest['source_sha256']}
Original CAD: {manifest.get('source_url','see source/SOURCES.json at the tool commit')}

Geometry remains DJI / RoboMaster property under upstream usage terms.
See NOTICE.md. The tooling's MIT/Apache licences do not relicense this CAD.

Reproduce from the tagged tooling source with the command in release.json.
ZIP entry timestamps are fixed; generated STEP provenance includes build time.
''')
        name=tag+'.zip';archive=stage/name
        sources=[*( (file,package/file) for file in FILES),('release.json',stage/'release.json'),('README.txt',readme)]
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
            for relative,path in sources:
                info=zipfile.ZipInfo(tag+'/'+relative,date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                with path.open('rb') as source,zipped.open(info,'w',force_zip64=True) as target:
                    shutil.copyfileobj(source,target,length=1024*1024)
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip() is not None:raise ValueError('archive CRC verification failed')
            for relative,expected in manifest['files_sha256'].items():
                with zipped.open(tag+'/'+relative) as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise ValueError('archive read-back checksum mismatch')
        (stage/'SHA256SUMS').write_text(''.join(f'{digest(stage/file)}  {file}\n' for file in [name,'release.json']))
        readme.unlink()
        stage.rename(out)
    return out/name


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--policy',type=Path,default=ROOT/'rules/hierarchy-rmuc2027.json')
    parser.add_argument('--tag',required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    if args.work.exists() or args.out.exists():raise ValueError('work and release outputs must be fresh')
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
    if dirty.strip():raise ValueError('commit tracked source changes before a release build')
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','python','rules','scripts/build_hierarchy_release.py'],cwd=ROOT,text=True)
    if untracked.strip():raise ValueError('commit untracked producer source before a release build')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    source=args.source.resolve();policy=args.policy.resolve()
    pin=json.loads(policy.read_text())['source_sha256']
    if digest(source)!=pin:raise ValueError('source does not match the hierarchy policy')
    command=[sys.executable,str(ROOT/'python/cad_hierarchy.py'),str(source),'--policy',str(policy),
             '--out',str(args.work.resolve()/'hierarchy'),'--validate-native']
    subprocess.run(command,cwd=ROOT,check=True)
    report,native=validate_package(args.work/'hierarchy',pin,args.baseline)
    sources=json.loads((ROOT/'source/SOURCES.json').read_text())['files']
    upstream=next(item for item in sources if item['sha256']==pin)
    tracked=subprocess.check_output(['git','ls-files','python','rules','scripts/build_hierarchy_release.py'],cwd=ROOT,text=True).splitlines()
    manifest={'schema_version':1,'pipeline_stage':1,'kind':'hierarchical-source-cad','runtime_ready':False,
              'tool_commit':commit,'source_file':upstream['name'],'source_sha256':pin,'source_url':upstream['url'],
              'geometry_modifications':False,'additional_sharing_passes_applied':[],
              'reviewed_baseline_matches':args.baseline is not None,
              'counts':{k:report[k] for k in ['work_part_definitions','source_face_definitions','expected_placed_faces',
                                             'source_body_definitions','source_placed_bodies','source_product_occurrences']},
              'native_validation':native,
              'producer_files_sha256':{file:digest(ROOT/file) for file in tracked},
              'environment':{'python':sys.version.split()[0],**{p:importlib.metadata.version(p) for p in ['cadquery-ocp','numpy']}},
              'reproduce':f'python scripts/build_hierarchy_release.py source/{upstream["name"]} --tag {args.tag} --work out/stage1-work --out out/stage1-release'}
    archive=package_release(args.work/'hierarchy',args.out,args.tag,manifest)
    print('Verified release archive:',archive,flush=True)


if __name__=='__main__':main()
