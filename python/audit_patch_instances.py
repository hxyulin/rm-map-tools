#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build and verify a source-owned affine patch layer and partial GLB inspection.

No installed package is changed. The GLB contains accepted definition-level
patches only; every unsupported face remains an explicit source fallback.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import time

import numpy as np
from cad_collision_roles import CollisionRoles
from cad_document import CadDocument
from cad_patch_instances import build_patch_instances,TEMPLATES
from export_field_package import GlbWriter
from gltf_scene import read_glb,write_glb,mesh_instances
from plan_cad_lods import digest
from cad_patch_storage import write_layer
from cad_archive import create_archive


def export_use(writer,use):
    """Share quad payloads; bake triangle shear into local coordinates for glTF."""
    positions,triangles=TEMPLATES[use.template];matrix=use.matrix_m()
    axes=matrix[:3,:3]/np.linalg.norm(matrix[:3,:3],axis=0)
    baked=False
    if not np.allclose(axes.T@axes,np.eye(3),rtol=0,atol=1e-10):
        origin,u,v=np.array(use.frame_mm);normal=np.cross(u,v);normal/=np.linalg.norm(normal)
        x=u/np.linalg.norm(u);y=np.cross(normal,x);rotation=np.column_stack((x,y,normal))
        positions=(use.positions_mm()-origin)@rotation/1000
        matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=origin/1000;baked=True
    writer.add_indexed_instance('face-'+str(use.source_face_id),positions,np.tile([0.,0,1],(len(positions),1)),triangles,
                                use.source_colour,matrix=matrix,
                                extras={'source_face_id':use.source_face_id,'component_id':use.component_id,
                                        'appearance_target_id':use.appearance_target_id,
                                        'role':use.collision_role,'collision':use.collision_role!='marking','inspection_only':True})
    return baked


def run(source,hierarchy,roles_path,output,*,budget_mm=1e-6):
    if output.exists():raise FileExistsError(output)
    hierarchy_sha=digest(hierarchy);catalog=json.loads(hierarchy.read_bytes())
    roles=CollisionRoles.read(roles_path,hierarchy) if roles_path else None
    started=time.perf_counter()
    with CadDocument.from_step(source,workers=1,intern_layers=True) as document:
        print('Source loaded; building finite instances',flush=True)
        layer=build_patch_instances(document,catalog,roles=roles,budget_mm=budget_mm)
        print('Accepted',len(layer.uses),'faces;',len(layer.fallback_face_ids),'source fallbacks',flush=True)
        writer=GlbWriter('SOURCE-PATCH-DEFINITIONS',{'version':'2.0','generator':'rm-map-tools affine patch inspection',
                          'copyright':'DJI / RoboMaster source geometry; this partial inspection is not a runtime package'})
        baked=sum(export_use(writer,use) for use in layer.uses)
        output.mkdir(parents=True)
        storage=write_layer(layer,output/'layer')
        import shutil
        shutil.copyfile(Path(__file__).resolve().parents[1]/'NOTICE.md',output/'layer/NOTICE.md')
        provenance={'source_sha256':document.source_sha256,'hierarchy_sha256':hierarchy_sha,
                    'roles_sha256':digest(roles_path) if roles_path else None,'budget_mm':budget_mm,
                    'producer_sha256':{name:digest(Path(__file__).with_name(name)) for name in
                                       ['cad_patch_instances.py','cad_patch_storage.py','audit_patch_instances.py']}}
        (output/'layer/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
        archive=create_archive(output/'layer',output/'patch-layer.tar.zst',level=22)
        writer.write(output/'accepted-patches.glb')
        doc,binary=read_glb(output/'accepted-patches.glb')
        # Preserve component ownership as an actual scene hierarchy, independently
        # of shared mesh/material handles. These are definitions, not placed uses.
        groups=defaultdict(list)
        for i,node in enumerate(doc['nodes'][1:],1):groups[node['extras']['component_id']].append(i)
        roots=[]
        for component,children in sorted(groups.items()):
            roots.append(len(doc['nodes']));doc['nodes'].append({'name':component,'children':children,
                                                               'extras':{'source_component_id':component}})
        doc['nodes'][0]['children']=roots
        write_glb(output/'accepted-patches.glb',doc,binary)
        by_face={u.source_face_id:u for u in layer.uses};maximum=0.;checked=0
        for node,_,points,triangles,_ in mesh_instances(doc,binary):
            face=doc['nodes'][node]['extras']['source_face_id'];use=by_face[face]
            error=float(np.linalg.norm(points*1000-use.positions_mm(),axis=1).max())
            maximum=max(maximum,error);checked+=1
            if error+use.boundary_error_bound_mm>.001:raise ValueError('inspection export exceeds 0.001 mm finite polygon margin')
            if len(triangles)!=len(TEMPLATES[use.template][1]):raise ValueError('template triangle coverage changed')
        if checked!=len(layer.uses):raise ValueError('instance export coverage changed')
        if digest(hierarchy)!=hierarchy_sha:raise ValueError('hierarchy input changed')
        document.verify_source()
        stats=layer.statistics();per_component=Counter(u.component_id for u in layer.uses)
        unshared_bytes=sum(TEMPLATES[u.template][0].shape[0]*24+TEMPLATES[u.template][1].size*2 for u in layer.uses)
        result={'source_sha256':document.source_sha256,'hierarchy_sha256':hierarchy_sha,
                'budget_mm':budget_mm,'statistics':stats,'rejection_counts':dict(layer.rejection_counts),
                'component_uses':dict(per_component),'glb':{'file':'accepted-patches.glb',
                    'sha256':digest(output/'accepted-patches.glb'),'file_bytes':(output/'accepted-patches.glb').stat().st_size,
                    'buffer_bytes':len(writer.bin),'unshared_template_buffer_bytes':unshared_bytes,
                    'geometry_payload_definitions':len(writer._indexed_payloads),'material_mesh_variants':len(writer.meshes),
                    'face_instance_nodes':len(layer.uses),'component_groups':len(groups),
                    'triangle_uses':writer.triangles,'triangles_with_shear_baked_to_local_geometry':baked,
                    'max_sampled_vertex_export_roundoff_mm':maximum,'roundtrip_instances_checked':checked},
                'compact_layer':storage,'archive':archive,
                'fallback_source_face_ids':list(layer.fallback_face_ids),
                'all_source_faces_accounted_once':len(layer.uses)+len(layer.fallback_face_ids)==layer.source_face_count,
                'original_source_unchanged':True,'elapsed_seconds':time.perf_counter()-started,
                'scope':'Optional finite source-polyline patch layer and partial definition-only GLB. Native surface/solid promotion, '
                        'full placed arena export, shared-boundary integration and runtime performance remain unmeasured.',
                'producer_sha256':{name:digest(Path(__file__).with_name(name)) for name in
                                   ['cad_patch_instances.py','cad_patch_storage.py','audit_patch_instances.py','export_field_package.py','cad_patch_matching.py','cad_shape_fitting.py','cad_archive.py']}}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'statistics':stats,'glb':result['glb'],'compact_layer':storage,
                      'archive_bytes':archive['archive_bytes']},indent=2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--hierarchy',type=Path,required=True)
    parser.add_argument('--roles',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--budget-mm',type=float,default=1e-6)
    args=parser.parse_args();run(args.source,args.hierarchy,args.roles,args.out,budget_mm=args.budget_mm)
