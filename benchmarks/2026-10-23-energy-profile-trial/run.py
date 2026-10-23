#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bounded complete-meridian Energy collision trial; never writes runtime assets."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'out/rmuc2027-energy-profile-trial'
sys.path[:0] = [str(ROOT / 'python'), str(ROOT / 'benchmarks/2026-10-17-collision-solids')]
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk
from audit import native, module
import validate as guards
from cad_collision_profiles import revolve_profile, mesh_metrics
from gltf_scene import read_glb, write_glb, accessor, scene_nodes, local_matrix
from mesh_quality import deviation, distances
from plan_cad_lods import digest
from simplify_package import append_accessor, scene_triangles

BASE = ROOT / 'out/rmuc2027-runtime-opportunities/refined/collision-1mm/arena-static-collision.glb'
CID = 'energy-unit/unit'

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')

def surface(a, at, b, bt):
    d = deviation(a, at, b, bt, count=max(len(at), len(bt)))
    d['maximum_vertex_distance_mm'] = float(max(distances(a[np.unique(at)], b, bt).max(), distances(b[np.unique(bt)], a, at).max()))
    return d

def clearance(p, t, source_ray):
    ray = guards.raycaster(p, t)
    shifts = []
    for radius in [0, 5, 10]:
        for angle in np.arange(16) * 2 * np.pi / 16:
            start = np.array([radius * np.cos(angle), -1., radius * np.sin(angle)])
            end = start + [0, 152, 0]
            a, b = source_ray(start, end), ray(start, end)
            if a is None or b is None: raise ValueError('missing socket stop')
            shifts.append(float(np.linalg.norm(a-b)))
    samples = np.array([[r*np.cos(a), y, r*np.sin(a)] for y in np.linspace(10,90,17) for r in [0,8,10] for a in np.arange(16)*2*np.pi/16])
    minimum = float(distances(samples,p,t).min())
    probes = np.array([[0.,50,0],[28,12,0],[0,130,0],[25,50,0]])
    points=vtk.vtkPoints();points.SetData(numpy_to_vtk(probes,deep=True));data=vtk.vtkPolyData();data.SetPoints(points)
    inside=vtk.vtkSelectEnclosedPoints();inside.SetInputData(data);inside.SetSurfaceData(guards.polydata(p,t));inside.Update()
    occupancy=[bool(inside.IsInside(i)) for i in range(4)]
    return {'socket_stop_rays':48,'maximum_socket_stop_shift_mm':max(shifts),'local_socket_stop_relief_allowance_mm':2,'sampled_projectile_centers':len(samples),'minimum_sampled_socket_surface_clearance_mm':minimum,'required_projectile_radius_mm':8.5,'socket_recess_occupancy':occupancy,'passed':max(shifts)<=2 and minimum>=8.5 and occupancy==[False,False,True,True]}

def owner_meshes(doc):
    inherited={}; result=[]
    for i,w,parent in scene_nodes(doc):
        inherited[i]=i if doc['nodes'][i].get('extras',{}).get('component_id')==CID else inherited.get(parent)
        if inherited[i] is not None and 'mesh' in doc['nodes'][i]: result.append((i,inherited[i],doc['nodes'][i]['mesh']))
    return result

def export(doc, blob, mesh_id, p, t, target):
    d=copy.deepcopy(doc);binary=bytearray(blob)
    xyz=(p[t]/1000).astype('<f4');positions=np.ascontiguousarray(xyz.reshape(-1,3))
    n=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    normals=np.ascontiguousarray(np.repeat(n[:,None],3,axis=1).reshape(-1,3),dtype='<f4')
    indices=np.arange(len(positions),dtype='<u4')
    prim=copy.deepcopy(d['meshes'][mesh_id]['primitives'][0])
    prim['attributes']={'POSITION':append_accessor(d,binary,positions,'VEC3',5126),'NORMAL':append_accessor(d,binary,normals,'VEC3',5126)}
    prim['indices']=append_accessor(d,binary,indices,'SCALAR',5125)
    prim.setdefault('extras',{}).update(energy_complete_profile_trial=True,angular_segments=len(t)//44,source_native_shell_index=1,collision_only=True)
    # Replace the single shared definition in place. Keep all original indices,
    # node extras, mesh reuse, and unrelated binary ranges literally unchanged.
    d['meshes'][mesh_id]['primitives']=[prim];d['buffers'][0]['byteLength']=len(binary)
    target.parent.mkdir(parents=True,exist_ok=True);write_glb(target,d,binary)
    rd,rb=read_glb(target)
    assert rd==d and rb[:len(blob)]==blob
    assert rd['nodes']==doc['nodes'] and rd['materials']==doc['materials']
    assert rd['scenes']==doc['scenes'] and owner_meshes(rd)==owner_meshes(doc)
    for mi,m in enumerate(doc['meshes']):
        if mi==mesh_id: continue
        assert rd['meshes'][mi]==m
        for pr in m['primitives']:
            for ai in [*pr['attributes'].values(),pr['indices']]: assert np.array_equal(accessor(doc,blob,ai),accessor(rd,rb,ai))
    qp=accessor(rd,rb,prim['attributes']['POSITION']).astype(float)*1000;qt=accessor(rd,rb,prim['indices']).reshape(-1,3)
    assert np.array_equal(qp[qt],xyz.astype(float)*1000)
    welded,inverse=np.unique(qp,axis=0,return_inverse=True);proof=mesh_metrics(welded,inverse[qt])
    assert proof['closed_oriented_manifold'] and proof['signed_volume_mm3']>0
    render=module('energy_render',ROOT/'benchmarks/2026-10-23-runtime-opportunities/render.py')
    data,owners=render.load_stage([('arena-static',target,[{}])])
    assert len(data[0])==scene_triangles(rd)
    assert sum(v['component_id']==CID for v in owners.values())==12
    return qp,qt,{'topology':proof,'scene_triangles':scene_triangles(rd),'stored_live_triangles':sum(len(accessor(rd,rb,pr['indices']))//3 for mi in {rd['nodes'][i]['mesh'] for i,_,_ in scene_nodes(rd) if 'mesh' in rd['nodes'][i]} for pr in rd['meshes'][mi]['primitives']),'sha256':digest(target),'bytes':target.stat().st_size,'preserved_all_other_arrays_materials_hierarchy_mesh_reuse':True,'render_load_stage_passed':True}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    summary_path=ROOT/'out/rmuc2027-collision-solids/energy-summary.json'
    summary=json.loads(summary_path.read_bytes())
    pinned=json.loads((ROOT/'benchmarks/2026-10-17-collision-solids/results.json').read_bytes())['energy-summary.json']
    assert summary==pinned, 'Energy summary differs from recorded qualified provenance'
    old=next(v for v in summary['variants'] if v['stage']=='meridian-1-24')
    folder=ROOT/'out/rmuc2027-collision-solids'/CID
    for name,h in old['outputs_sha256'].items(): assert digest(folder/name)==h
    source=ROOT/'out/rmuc2027-equipment-pipeline'/CID/'source.step'
    native_path=source.with_name('native.npz')
    assert digest(source)==summary['source_step_sha256'] and digest(native_path)==summary['native_npz_sha256']
    assert digest(ROOT/'python/cad_collision_profiles.py')==summary['pass_sha256']
    assert digest(ROOT/'benchmarks/2026-10-17-collision-solids/energy.py')==summary['producer_sha256']
    loops=old['meridian_loops'];orig=np.load(folder/'meridian-1-24.npz');rp,rt,_=revolve_profile(loops,angular_segments=24)
    assert np.array_equal(rp,orig['positions_mm']) and np.array_equal(rt,orig['triangles'])
    refined_path=ROOT/'out/rmuc2027-runtime-opportunities/refined.json'; refined=json.loads(refined_path.read_bytes())
    doc,blob=read_glb(BASE); assert digest(BASE)==refined['assets']['arena-static/collision']['sha256']
    selected=owner_meshes(doc);assert len(selected)==12 and len({x[2] for x in selected})==1
    mi=selected[0][2]; assert {i for i,n in enumerate(doc['nodes']) if n.get('mesh')==mi}=={r[0] for r in selected}
    pr=doc['meshes'][mi]['primitives'][0]; assert len(doc['meshes'][mi]['primitives'])==1
    bp=accessor(doc,blob,pr['attributes']['POSITION']).astype(float)*1000;bt=accessor(doc,blob,pr['indices']).reshape(-1,3)
    assert len(bt)==784 and pr['material']==2
    for node,owner,_ in selected:
        assert doc['nodes'][node]['extras']['collision_only']
        assert doc['nodes'][node]['extras']['derived_geometry']
        assert np.array_equal(local_matrix(doc['nodes'][node]),np.eye(4))
    original=np.load(native_path);np_=original['positions_mm'];nt=original['triangles'][original['unit_ids']==1]
    _,_,faces,shells,owners=native(source)
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopoDS import TopoDS
    support=BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(609))).Cylinder()
    assert owners[609]==1 and abs(support.Radius()-20)<1e-6 and np.allclose(np.abs(support.Axis().Direction().Coord()),[0,1,0],atol=1e-8) and np.linalg.norm(np.array(support.Location().Coord())[[0,2]])<1e-6
    source_ray=guards.source_raycaster(shells.FindKey(1))
    protected=[p for p in (ROOT.parent/'rm-simulator/field-2027').rglob('*') if p.is_file()]
    hashes={str(p):digest(p) for p in protected}
    trials=[];mappings=[]
    for segments in [16,12,8]:
        p,t,topology=revolve_profile(loops,angular_segments=segments)
        # Test the actual float32 export payload, including roundtrip error.
        p=(p/1000).astype(np.float32).astype(float)*1000
        native_error=surface(np_,nt,p,t);accepted_error=surface(bp,bt,p,t);checks=clearance(p,t,source_ray)
        passed=max(native_error['max'],native_error['maximum_vertex_distance_mm'])<=6 and checks['passed'] and len(t)<len(bt)
        row={'angular_segments':segments,'triangles':len(t),'actual_baseline_triangles':len(bt),'placed_saving':(len(bt)-len(t))*12,'native_exterior_deviation_mm':native_error,'accepted_collider_deviation_mm':accepted_error,'topology':topology,'clearance':checks,'passes_original_6mm_guard':passed,'status':'qualifying-local-trial' if passed else 'rejected-original-6mm-policy'}
        # Export all three for matched inspection; rejected files are never a mapping default.
        target=OUT/f'segments-{segments}'/'arena-static-collision.glb'
        ep,et,verified=export(doc,blob,mi,p,t,target); row['output']={'path':str(target),'role':'collision','asset':'arena-static',**verified}
        row['exported_clearance']=clearance(ep,et,source_ray);assert row['exported_clearance']['passed']
        row['map_collision_placed_triangles']=196332-row['placed_saving']
        assert verified['scene_triangles']==67315-row['placed_saving']
        trials.append(row)
        if passed: mappings.append({'baseline_path':str(BASE),'baseline_sha256':digest(BASE),'output_path':str(target),'output_sha256':digest(target),'role':'collision','asset':'arena-static','angular_segments':segments,'baseline_scene_triangles':67315,'output_scene_triangles':verified['scene_triangles'],'baseline_map_collision_placed_triangles':196332,'output_map_collision_placed_triangles':row['map_collision_placed_triangles'],'placed_triangle_reduction':row['placed_saving'],'status':'qualifying-local-trial-not-installed'})
        print(json.dumps(row),flush=True)
    assert all(digest(Path(p))==h for p,h in hashes.items()), 'installed runtime changed'
    report={'component_id':CID,'source_native_shell_index':1,'baseline':{'path':str(BASE),'sha256':digest(BASE),'role':'collision','asset':'arena-static','scene_triangles':scene_triangles(doc),'energy_triangles_per_unit':len(bt),'energy_placements':12,'energy_shared_mesh':mi,'energy_owner_rows':selected},'source':{'summary_path':str(summary_path),'summary_sha256':digest(summary_path),'stage':'meridian-1-24','step_path':str(source),'step_sha256':digest(source),'native_npz_path':str(native_path),'native_npz_sha256':digest(native_path),'meridian_loops':loops,'refined_json_path':str(refined_path),'refined_json_sha256':digest(refined_path)},'policy':{'native_exterior_guard_mm':6,'guard':'original deterministic bidirectional sampled surface and all used vertices; actual float32 exported geometry','allowed_loss':'Only angular faceting of the checksum-qualified original complete meridian; original 1 mm meridian simplification and symmetry approximation retained. No profile/recess deletion, outer-radius fit, socket closure, visual or optical edit. Blue diagnostic collision material retained exactly.','clearance':'48 original source CAD stop rays <=2 mm; 816 finite projectile centers >=8.5 mm surface clearance; original socket/recess occupancy probes; closed outward edge manifold.','limits':'Finite diagnostics, not continuous Hausdorff/CAD, full trajectory or motion certificates. Local trial only, no new guard approved. Rejected exports are inspection comparisons only.','storage':'Original binary prefix retained to guarantee unrelated data identity; obsolete Energy accessors remain orphaned, so file bytes need not shrink.'},'trials':trials,'qualifying_mappings':mappings,'preferred_mapping':min(mappings,key=lambda m:m['output_scene_triangles']) if mappings else None,'verification':{'installed_runtime_files_rehashed_unchanged':len(hashes),'baseline_rehashed_unchanged':digest(BASE)==refined['assets']['arena-static/collision']['sha256']},'producer_sha256':digest(Path(__file__))}
    dump(OUT/'results.json',report)
    dump(HERE/'results.json',{'report_path':str(OUT/'results.json'),'report_sha256':digest(OUT/'results.json'),'producer_sha256':digest(Path(__file__)),'preferred_mapping':report['preferred_mapping'],'trial_summary':[{k:r[k] for k in ['angular_segments','triangles','placed_saving','passes_original_6mm_guard','map_collision_placed_triangles']} for r in trials]})

if __name__=='__main__': main()
