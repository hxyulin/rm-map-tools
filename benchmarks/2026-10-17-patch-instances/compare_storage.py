#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare packed affine tables with equivalent expanded finite patch corners.

The control retains the same source/style/role/proof/fallback tables. It replaces
frames with reconstructed polygon corners, not a complete alternative CAD format.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_archive import create_archive
from cad_patch_storage import read_layer
from plan_cad_lods import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    manifest=json.loads((args.package/'layer/manifest.json').read_text())
    layer=read_layer(args.package/'layer',expected_source_sha256=manifest['source_sha256'])
    with np.load(args.package/'layer/instances.npz',allow_pickle=False) as archive:tables={k:archive[k] for k in archive.files}
    geometry_keys={'frames_mm','origins_mm','edge_vectors_mm','edge_vector_indices'}
    control={k:v for k,v in tables.items() if k not in geometry_keys}
    positions=np.concatenate([u.positions_mm() for u in layer.uses])
    control['expanded_positions_mm']=positions
    folder=args.out/'expanded-control';folder.mkdir(parents=True)
    np.savez(folder/'instances.npz',**control)
    header={**manifest,'schema':'rm-expanded-patch-comparison-v1','frame_encoding':'expanded-corners',
            'instances_sha256':digest(folder/'instances.npz')}
    (folder/'manifest.json').write_text(json.dumps(header,indent=2)+'\n')
    for name in ('NOTICE.md','provenance.json'):shutil.copyfile(args.package/'layer'/name,folder/name)
    with np.load(folder/'instances.npz',allow_pickle=False) as check:
        assert np.array_equal(check['expanded_positions_mm'],positions)
        for k in control.keys()-{'expanded_positions_mm'}:assert np.array_equal(check[k],tables[k])
    archive=create_archive(folder,args.out/'expanded-control.tar.zst',level=22)
    packed=json.loads((args.package/'summary.json').read_text())
    result={'source_sha256':manifest['source_sha256'],'same_non_geometry_tables':True,
            'expanded_corner_coordinates_checked':len(positions),
            'packed_array_bytes':sum(a.nbytes for a in tables.values()),'expanded_array_bytes':sum(a.nbytes for a in control.values()),
            'packed_level22_bytes':packed['archive']['archive_bytes'],'expanded_level22_bytes':archive['archive_bytes'],
            'scope':'Same reconstructed finite patch corners and non-geometry metadata; neither package includes native fallback geometry. '
                    'Expanded control preserves reconstructed corners, while packed tables preserve original affine-frame values bit-for-bit.',
            'producer_sha256':digest(__file__)}
    (args.out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
