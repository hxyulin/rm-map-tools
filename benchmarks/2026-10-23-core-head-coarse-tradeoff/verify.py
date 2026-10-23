"""Quantify coarse contact tradeoffs without treating source fidelity as a veto."""
import json
from pathlib import Path
import numpy as np
import vtk
from scipy.spatial import ConvexHull
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from build import ROOT,OUT,PREVIOUS,p,v,scan

def locator(g):
    pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(g.reshape(-1,3).astype(float),deep=True));cells=vtk.vtkCellArray()
    cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(len(g)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True))
    poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();return loc

def rays(loc,xy):
    t=vtk.reference(0.);sub=vtk.reference(0);cell=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.];result=[]
    for x,y in xy:
        hit=loc.IntersectWithLine([x,y,-800.],[x,y,-350.],1e-7,t,point,pc,sub,cell);result.append(float(t)*450 if hit else np.nan)
    return np.array(result)

def surfaces(shapes):return [v.geometry(s)for s in shapes]

def covered(points,shape,strict=False):
    matrix=__import__('scipy').spatial.transform.Rotation.from_quat(shape['pose']['rotation_xyzw']).as_matrix()
    q=(points-np.array(shape['pose']['translation_m'])*1000)@matrix
    eps=-1e-6 if strict else 1e-6
    if shape['kind']=='box':return np.max(abs(q)-np.array(shape['half_extents_m'])*1000,axis=1)<=eps
    if shape['kind']=='cylinder':return (np.linalg.norm(q[:,:2],axis=1)<=shape['radius_m']*1000+eps)&(abs(q[:,2])<=shape['length_m']*500+eps)
    hull=ConvexHull(np.array(shape['vertices_local_m'])*1000)
    return (q@hull.equations[:,:3].T+hull.equations[:,3]).max(1)<=eps

def uncovered_distance(points,shapes,retained):
    inside=np.zeros(len(points),bool)
    for shape in shapes:inside|=covered(points,shape)
    remaining=points[~inside];dist=np.zeros(len(points))
    if not len(remaining):return dist
    candidates=[]
    for s,g in zip(shapes,surfaces(shapes)):
        if s['kind']=='box':
            matrix=__import__('scipy').spatial.transform.Rotation.from_quat(s['pose']['rotation_xyzw']).as_matrix()
            q=abs((remaining-np.array(s['pose']['translation_m'])*1000)@matrix)-np.array(s['half_extents_m'])*1000
            candidates.append(np.linalg.norm(np.maximum(q,0),axis=1))
        elif s['kind']=='cylinder':
            matrix=__import__('scipy').spatial.transform.Rotation.from_quat(s['pose']['rotation_xyzw']).as_matrix()
            q=(remaining-np.array(s['pose']['translation_m'])*1000)@matrix
            candidates.append(np.linalg.norm(np.maximum(np.column_stack([np.linalg.norm(q[:,:2],axis=1)-s['radius_m']*1000,abs(q[:,2])-s['length_m']*500]),0),axis=1))
        else:candidates.append(p.distances(remaining,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3)))
    candidates.append(p.distances(remaining,retained.reshape(-1,3),np.arange(len(retained)*3).reshape(-1,3)))
    dist[~inside]=np.min(candidates,axis=0);return dist

def main(approach_exempt_labels=()):
    results=[]
    manifest_path=ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json';manifest=json.loads(manifest_path.read_text())
    assert not any(k in manifest['assets']['tech-core']for k in ['semantics','motion','joints'])
    for item in json.loads((OUT/'variants.json').read_text()):
        path=Path(item['path']);r=json.loads(path.read_text());assert scan.digest(path)==item['sha256']
        for source,h in r['input_pins'].items():assert scan.digest(Path(source))==h
        source=Path(r['source_collision']);target=Path(r['candidate_collision']);d,c,n=scan.load_nodes(source);a,ab=p.read_glb(target);_,_,nn=scan.load_nodes(target)
        assert scan.digest(target)==r['candidate_sha256'];exact=p.pair.unchanged(source,target,set(r['grouped_head_nodes']))
        assert scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
        for i in r['kept_head_nodes']:assert np.array_equal(n[i],nn[i])
        for i in r['grouped_head_nodes']:
            assert c[i]=='technology-core/tool-head'
            if i!=1668:assert 'mesh'not in a['nodes'][i]
        recipe=json.loads(Path(r['native_review']).read_text());head_parts=[part for part in recipe['native_parts']if part.get('source_group')=='rigid-head-envelope'];shapes=[part['shape']for part in head_parts]
        assert len(shapes)==r['head_native_shapes']
        old_report=json.loads((PREVIOUS/'verification.json').read_text());old_recipe=json.loads(Path(old_report['native_review']).read_text())
        expected_arm=[part for part in old_recipe['native_parts']if part['component_id']!='technology-core/tool-head']
        assert [part for part in recipe['native_parts']if part.get('source_group')!='rigid-head-envelope']==expected_arm
        for s in shapes:
            assert np.isfinite(s['pose']['translation_m']).all()and abs(np.linalg.norm(s['pose']['rotation_xyzw'])-1)<1e-10
            if s['kind']=='box':assert min(s['half_extents_m'])>0
            elif s['kind']=='cylinder':assert s['radius_m']>0 and s['length_m']>0
            else:assert ConvexHull(np.array(s['vertices_local_m'])).volume>0
        assert not d.get('animations')and not d.get('skins')
        for i,world,parent in p.scene_nodes(d):
            if i==3 or i in r['grouped_head_nodes']:assert np.array_equal(world,np.eye(4))
        # Both approach channels stay empty of NEW housing shapes before the
        # original backing plate. Retained precise socket meshes remain present.
        sleeve=np.array([[x,y,z]for x in [-624.,-612.5,-601.]for y in np.linspace(-870,-707,25)for z in [-533.,-521.5,-510.]])
        nose=np.array([[x,y,z]for x in [-631.,-611.5,-592.]for y in [-773.,-752.5,-732.]for z in np.linspace(-699,-490,25)])
        checked_shapes=[s for s,label in zip(shapes,r['definition']['labels'])if label not in approach_exempt_labels]
        assert not any(covered(sleeve,s,strict=True).any()for s in checked_shapes)
        assert not any(covered(nose,s,strict=True).any()for s in checked_shapes)
        head={i for i in n if c[i]=='technology-core/tool-head'};old_geo=np.concatenate([n[i]for i in head]);new_geo=np.concatenate([nn[i]for i in head if i in nn])
        xy=np.array([[x,y]for x in np.arange(-690,-530+1e-6,2)for y in np.arange(-900,-670+1e-6,2)])
        old=rays(locator(old_geo),xy);new=rays(locator(new_geo),xy);both=np.isfinite(old)&np.isfinite(new);delta=abs(old[both]-new[both])
        contact=dict(probes=len(xy),source_hits=int(np.isfinite(old).sum()),candidate_hits=int(np.isfinite(new).sum()),
            hit_state_changes=int((np.isfinite(old)!=np.isfinite(new)).sum()),max_common_hit_shift_mm=float(delta.max()),
            common_hit_shift_over_1mm=int((delta>1).sum()),common_hit_shift_over_10mm=int((delta>10).sum()),common_hit_shift_over_25mm=int((delta>25).sum()),
            caveat='Changes are reported tradeoffs, not zero-error acceptance tests. Grid covers the same central interface as earlier reviews.')
        points=p.probes(old_geo,20000);retained=np.concatenate([n[i]for i in r['kept_head_nodes']]);outside=uncovered_distance(points,shapes,retained)
        proxy=nn[1668];reverse=p.distances(p.probes(proxy,30000),old_geo.reshape(-1,3),np.arange(len(old_geo)*3).reshape(-1,3))
        fit=dict(source_uncovered_max_mm=float(outside.max()),source_uncovered_p99_mm=float(np.quantile(outside,.99)),
            source_probes_over_10mm=int((outside>10).sum()),source_probes_over_25mm=int((outside>25).sum()),source_probes=len(points),
            proxy_surface_to_source_max_mm=float(reverse.max()),proxy_surface_to_source_p99_mm=float(np.quantile(reverse,.99)),
            caveat='Source points inside a new solid count as covered. Reverse distances include deliberate internal filling and child interfaces, not just silhouette error.')
        rd,rb=p.read_glb(Path(r['native_review']).parent/'remainder.glb');assert p.scene_triangles(rd)==r['native_remaining_mesh_per_core']
        native_source=Path(recipe['source']['file']);assert scan.digest(native_source)==recipe['source']['sha256']
        assert scan.digest(Path(r['native_review']).parent/'remainder.glb')==recipe['retained_mesh']['sha256']
        p.pair.unchanged(native_source,Path(r['native_review']).parent/'remainder.glb',set(recipe['replaced_node_indices']))
        stage=json.loads((path.parent/'paired-stage.json').read_text())
        for role in ['visual','collision']:
            assert sum(e['placed_triangles']for e in stage[f'{role}_assets'].values())==stage[f'placed_{role}_triangles']
            for entry in stage[f'{role}_assets'].values():assert scan.digest(Path(entry['path']))==entry['sha256']
        for g in surfaces(shapes):
            assert np.isfinite(g).all()and np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-9
            assert np.einsum('ij,ij->i',g[:,0],np.cross(g[:,1],g[:,2])).sum()>0
        result=dict(variant=r['variant'],visual_exact=True,source_node_metadata_and_other_arrays_exact=True,unchanged_preview_owners_exact=exact,
            grouped_head_rigidity_checked_against_current_manifest=True,existing_39_arm_cylinders_exact=True,protected_approach_samples=len(sleeve)+len(nose),contact_grid=contact,fit=fit,
            head_native_shapes=len(shapes),head_mesh_triangles=r['head_mesh_triangles_kept'],runtime_supported=False,contact_validated=False)
        if approach_exempt_labels:result['approach_clearance_exempt_shape_labels']=list(approach_exempt_labels)
        (path.parent/'geometry-verification.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
        print(r['variant'],'contacts',contact,'fit',fit,flush=True)
    (OUT/'geometry-verification.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
