"""Exact preserved payloads plus bounded front-interface ray comparisons."""
import json
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from survey import ROOT,OUT,p
from build import omissions,support

def locator(g):
    points=vtk.vtkPoints();points.SetData(numpy_to_vtk(g.reshape(-1,3).astype(float),deep=True))
    cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(len(g)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True))
    poly=vtk.vtkPolyData();poly.SetPoints(points);poly.SetPolys(cells)
    loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();return loc

def first_hits(loc,xy):
    t=vtk.reference(0.);sub=vtk.reference(0);cell=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.];out=[]
    for x,y in xy:
        hit=loc.IntersectWithLine([x,y,-800.],[x,y,-350.],1e-7,t,point,pc,sub,cell)
        out.append(float(t)*450 if hit else np.nan)
    return np.array(out)

def box_outside(points,definition):
    q=points@np.array(definition['frame_columns']);values=[]
    for lo,hi in definition['boxes_bounds_mm']:
        lo=np.array(lo);hi=np.array(hi);v=abs(q-(lo+hi)/2)-(hi-lo)/2
        values.append(np.linalg.norm(np.maximum(v,0),axis=1)+np.minimum(v.max(1),0))
    return np.min(values,axis=0)

def recess_hits(loc,frame):
    values=[];t=vtk.reference(0.);sub=vtk.reference(0);cell=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.]
    for x in np.arange(-640.,-594.+1e-6,2.):
        for y in [-935.,-934.,-933.,-932.]:
            start=np.array([x,y,-500.])@frame.T;end=np.array([x,y,-390.])@frame.T
            hit=loc.IntersectWithLine(start,end,1e-7,t,point,pc,sub,cell);values.append(float(t)*110 if hit else np.nan)
    return np.array(values)

def main():
    survey=json.loads((OUT/'survey.json').read_text());source=Path(survey['source']);d,c,n=p.scan.load_nodes(source)
    head={i for i in n if c[i]=='technology-core/tool-head'};oldloc=locator(np.concatenate([n[i]for i in head]))
    xy=np.array([[x,y]for x in np.arange(-690.,-530.+1e-6,2.)for y in np.arange(-900.,-670.+1e-6,2.)])
    before=first_hits(oldloc,xy);results=[]
    for variant in json.loads((OUT/'variants.json').read_text()):
        report_path=Path(variant['path']);r=json.loads(report_path.read_text());assert p.scan.digest(report_path)==variant['sha256']
        for path,h in r['input_pins'].items():assert p.scan.digest(Path(path))==h
        target=Path(r['candidate_collision']);assert p.scan.digest(target)==r['candidate_sha256']
        limit=int(r['variant'].split('-')[1][:-2]);ids,guard=omissions(d,c,n,limit);assert ids==[x['node']for x in r['omitted_collision_owners']]
        assert guard==r['guarded_compact_owners']
        exact=p.pair.unchanged(Path(r['approved_collision']),target,set(ids)|{1668})
        td,tb=p.read_glb(target);_,_,nodes=p.scan.load_nodes(target)
        for i in ids:assert 'mesh'not in td['nodes'][i]
        assert 108 in nodes and np.array_equal(nodes[108],n[108])
        for i in [82,81,1284,1296,1297,1501]:assert np.array_equal(nodes[i],n[i])
        expected,definition=support();np.testing.assert_allclose(nodes[1668],expected,rtol=0,atol=.0002)
        assert len(nodes[1668])==84
        after=first_hits(locator(np.concatenate([nodes[i]for i in head if i in nodes])),xy)
        both=np.isfinite(before)&np.isfinite(after);delta=abs(before[both]-after[both]);changed=delta>.0005
        ray_report=dict(probes=len(xy),before_hits=int(np.isfinite(before).sum()),after_hits=int(np.isfinite(after).sum()),
            changed_hit_state=int((np.isfinite(before)!=np.isfinite(after)).sum()),max_common_first_hit_change_mm=float(delta.max()),
            changed_over_0_0005mm=int(changed.sum()),grid_source_mm=dict(x=[-690,-530],y=[-900,-670],pitch=2,z=[-800,-350]))
        assert ray_report['changed_hit_state']==0 and ray_report['changed_over_0_0005mm']==0
        outside=box_outside(p.probes(n[1668]),definition)
        assert outside.max()<3.
        frame=np.array(definition['frame_columns']);recess_before=recess_hits(locator(n[1668]),frame);recess_after=recess_hits(locator(nodes[1668]),frame)
        assert np.isfinite(recess_before).all()and np.isfinite(recess_after).all()
        recess_error=float(abs(recess_before-recess_after).max());assert recess_error<.001
        # Real source protrusions vs interior depth are separate quantities.
        native=json.loads((report_path.parent/'native/collision-shapes.json').read_text());nd,nb=p.read_glb(report_path.parent/'native/remainder.glb')
        assert native['source']['sha256']==r['head_source_sha256']==p.scan.digest(Path(r['head_source']))
        assert native['retained_mesh']['sha256']==p.scan.digest(report_path.parent/'native/remainder.glb')
        assert native['retained_mesh']['triangles']==p.scene_triangles(nd)==r['native_remaining_mesh_per_core']
        assert len(native['native_parts'])==39
        approved_native=json.loads((ROOT/'out/rmuc2027-core-arm-checkpoint/native/collision-shapes.json').read_text())
        assert [(x['id'],x['shape'])for x in native['native_parts']]==[(x['id'],x['shape'])for x in approved_native['native_parts']]
        assert p.scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
        results.append(dict(variant=r['variant'],unchanged_collision_owners_exact=exact,visual_file_exact=True,
            front_grill_and_named_tool_contact_owners_exact=True,interface_first_hit_rays=ray_report,
            support_source_outside_solid_union_max_mm=float(max(0,outside.max())),support_signed_inside_depth_mm=float(max(0,-outside.min())),
            rear_recess_rays=dict(probes=len(recess_before),max_first_hit_change_mm=recess_error),
            preserved_arm_native_cylinders=39,head_triangles=r['candidate_head_triangles'],placed_mesh_saving=r['placed_mesh_saving']))
    output=dict(variants=results,installed=False,contact_validated=False,
        limits='Only first hits along the stated source-Z interface grid are qualified. Exterior small-detail contacts, oblique rays, all poses and motion are not approved.')
    (OUT/'geometry-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(results),flush=True)

if __name__=='__main__':main()
