"""Reopen mixed review vectors and preserve frontal/recess ray behavior."""
import json
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from research import ROOT,OUT,p,scan
from build import geometry

def locator(g):
    points=vtk.vtkPoints();points.SetData(numpy_to_vtk(g.reshape(-1,3).astype(float),deep=True))
    cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(len(g)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True))
    poly=vtk.vtkPolyData();poly.SetPoints(points);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();return loc

def ray_hits(loc,lines):
    values=[];t=vtk.reference(0.);sub=vtk.reference(0);cell=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.]
    for start,end in lines:
        hit=loc.IntersectWithLine(start,end,1e-7,t,point,pc,sub,cell)
        values.append(float(t)*np.linalg.norm(np.array(end)-start)if hit else np.nan)
    return np.array(values)

def main():
    r=json.loads((OUT/'verification.json').read_text());source=Path(r['source_collision']);target=Path(r['candidate_collision'])
    for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
    assert scan.digest(source)==r['source_collision_sha256'];assert scan.digest(target)==r['candidate_sha256']
    assert scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
    exact=p.pair.unchanged(source,target,set(r['changed_head_nodes']))
    d,c,before=scan.load_nodes(source);td,tb=p.read_glb(target);_,_,after=scan.load_nodes(target)
    head={i for i in before if c[i]=='technology-core/tool-head'}
    xy=np.array([[x,y]for x in np.arange(-690.,-530.+1e-6,2.)for y in np.arange(-900.,-670.+1e-6,2.)])
    lines=[([x,y,-800.],[x,y,-350.])for x,y in xy]
    first=ray_hits(locator(np.concatenate([before[i]for i in head])),lines);second=ray_hits(locator(np.concatenate([after[i]for i in head])),lines)
    both=np.isfinite(first)&np.isfinite(second);ray_delta=float(abs(first[both]-second[both]).max())
    assert np.array_equal(np.isfinite(first),np.isfinite(second))and ray_delta<.0005
    support_report=json.loads(Path(r['accepted_head_report']).read_text());frame=np.array(support_report['support_definition']['frame_columns'])
    recess_lines=[(np.array([x,y,-500.])@frame.T,np.array([x,y,-390.])@frame.T)for x in np.arange(-640.,-594.+1e-6,2.)for y in [-935.,-934.,-933.,-932.]]
    old_recess=ray_hits(locator(before[1668]),recess_lines);new_recess=ray_hits(locator(after[1668]),recess_lines)
    assert np.isfinite(old_recess).all()and np.isfinite(new_recess).all();recess_delta=float(abs(old_recess-new_recess).max());assert recess_delta<.001
    recipe_path=Path(r['native_review']);recipe=json.loads(recipe_path.read_text());native_source=Path(recipe['source']['file'])
    assert recipe['schema']=='rm-map-tools.native-primitive-review-1'and not recipe['runtime_supported']
    assert scan.digest(native_source)==recipe['source']['sha256']
    remainder=recipe_path.parent/'remainder.glb';assert scan.digest(remainder)==recipe['retained_mesh']['sha256']
    rd,rb=p.read_glb(remainder);assert p.scene_triangles(rd)==recipe['retained_mesh']['triangles']==r['native_remaining_mesh_per_core']
    native_exact=p.pair.unchanged(native_source,remainder,set(recipe['replaced_node_indices']))
    source_doc,_=p.read_glb(native_source);parents={i:parent for i,w,parent in p.scene_nodes(source_doc)}
    ids=set();new_parts={}
    for part in recipe['native_parts']:
        assert part['id']not in ids;ids.add(part['id']);i=part['source_node_index'];assert 'mesh'not in rd['nodes'][i]
        assert part['source_node_name']==source_doc['nodes'][i]['name'];anc=[];j=i
        while j is not None:anc.append(j);j=parents[j]
        assert anc[::-1]==part['ancestor_nodes_root_first']
        s=part['shape'];quat=np.array(s['pose']['rotation_xyzw']);assert abs(np.linalg.norm(quat)-1)<1e-10
        assert np.isfinite(s['pose']['translation_m']).all()
        if s['kind']=='box':assert min(s['half_extents_m'])>0
        if s['kind']=='convex_hull':assert ConvexHull(np.array(s['vertices_local_m'])).volume>0 and len(s['vertices_local_m'])<=64
        if s['kind']!='cylinder':new_parts.setdefault(i,[]).append(geometry(s))
    for i,pieces in new_parts.items():
        g=np.concatenate(pieces);dist=p.distances(p.probes(after[i],5000),g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3));assert dist.max()<.0003
    for row in r['measurements']:
        i=row['node'];g=after[i]
        assert np.isfinite(g).all()and np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-9
        if i!=1668:
            fwd=p.distances(p.probes(before[i],50000),g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3))
            rev=p.distances(p.probes(g,50000),before[i].reshape(-1,3),np.arange(len(before[i])*3).reshape(-1,3))
            assert max(fwd.max(),rev.max())<2.
    stage=json.loads((OUT/'paired-stage.json').read_text());accepted=json.loads((Path(r['accepted_head_report']).parent/'paired-stage.json').read_text())
    assert stage['visual_assets']==accepted['visual_assets']
    for asset,entry in accepted['collision_assets'].items():
        if asset!='tech-core':assert stage['collision_assets'][asset]==entry
    for role in ['visual','collision']:
        assert sum(x['placed_triangles']for x in stage[f'{role}_assets'].values())==stage[f'placed_{role}_triangles']
    counts=recipe['shape_counts'];assert counts=={'cylinder':39,'box':7,'convex_hull':4}
    old_native=json.loads((Path(r['accepted_head_report']).parent/'native/collision-shapes.json').read_text())
    assert [part for part in recipe['native_parts']if part['shape']['kind']=='cylinder']==old_native['native_parts']
    head_count=sum(len(before[i])for i in r['changed_head_nodes']);assert head_count==661
    assert r['field_native_mesh_triangles']==444187
    output=dict(approved_visual_exact=True,unselected_collision_owners_exact=exact,native_remainder_owners_exact=native_exact,
        front_interface_rays=dict(count=len(xy),hit_state_changes=0,max_common_first_hit_change_mm=ray_delta),
        rear_recess_rays=dict(count=len(old_recess),max_first_hit_change_mm=recess_delta),
        native_counts_per_core=counts,box_hull_points_poses_dimensions_and_source_ownership_verified=True,
        existing_39_cylinders_preserved=True,runtime_supported=False,installed=False,contact_validated=False)
    (OUT/'geometry-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Mixed fit verified:',counts,'front rays',len(xy),'unchanged; native remainder',recipe['retained_mesh']['triangles'])

if __name__=='__main__':main()
