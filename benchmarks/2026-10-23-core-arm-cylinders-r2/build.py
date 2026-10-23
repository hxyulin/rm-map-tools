"""Expand the reviewed arm collision to native tubes and motor compounds.

Visual assets and all earlier candidates remain immutable. Every replacement
stays under its original source owner, including intersecting cylinder children.
"""
import copy,importlib.util,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
spec=importlib.util.spec_from_file_location('prior_arm',ROOT/'benchmarks/2026-10-23-core-arm-proxies/build.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
scan=prior.scan
from collision_shape_export import export as export_native
OUT=ROOT/'out/rmuc2027-core-arm-cylinders-r2'
PREVIOUS=ROOT/'out/rmuc2027-core-arm-proxies'

def read_source_faces():
    """Read the same XCAF shell/face ordering as the source native tessellator."""
    from validate_parts import read_part
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.collections import Sequence_TDF_Label,IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    from OCP.TopoDS import TopoDS_Compound,TopoDS
    from OCP.BRep import BRep_Builder
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_FACE,TopAbs_SHELL
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    path=ROOT/'out/rmuc2027-equipment-pipeline/technology-core/arm-and-shared/source.step'
    d,_,err=read_part(str(path));assert not err
    st=XCAFDoc_DocumentTool.ShapeTool_s(d.Main());roots=Sequence_TDF_Label();st.GetFreeShapes(roots)
    root=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(root)
    for i in range(1,roots.Length()+1):builder.Add(root,st.GetShape_s(roots.Value(i)))
    faces=ShapeMap();shells=ShapeMap();TopExp.MapShapes_s(root,TopAbs_FACE,faces);TopExp.MapShapes_s(root,TopAbs_SHELL,shells)
    assert faces.Extent()==628 and shells.Extent()==52
    rows=[]
    for sh in [26,33]:
        owned=ShapeMap();TopExp.MapShapes_s(shells.FindKey(sh),TopAbs_FACE,owned)
        for i in range(1,owned.Extent()+1):
            face=owned.FindKey(i);s=BRepAdaptor_Surface(TopoDS.Face(face))
            if s.GetType()!=GeomAbs_Cylinder:continue
            c=s.Cylinder();axis=np.array(c.Axis().Direction().Coord());point=np.array(c.Location().Coord())
            rows.append(dict(shell_ordinal=sh,face_ordinal=faces.FindIndex(face),radius_mm=c.Radius(),axis=axis.tolist(),point_mm=point.tolist(),
                support_v_bounds_mm=[s.FirstVParameter(),s.LastVParameter()]))
    return path,rows

def source_axis(source_faces,face,expected_shell,expected_radius):
    row=next(r for r in source_faces if r['face_ordinal']==face)
    assert row['shell_ordinal']==expected_shell and abs(row['radius_mm']-expected_radius)<.001
    a=np.array(row['axis']);a*=1 if a[np.argmax(abs(a))]>0 else -1
    return np.array(row['point_mm']),a

def interval(c,a,r,lo,hi):
    assert hi>lo
    return prior.shape(np.asarray(c)+np.asarray(a)*(lo+hi)/2,a,r,hi-lo)

def surface_samples(s,angular=144,axial=61):
    """Round analytic surfaces, without diagnostic polygon inflation."""
    a,u,v=prior.basis(s['axis_unit_vector']);c=np.array(s['center_m'])*1000;r=s['radius_m']*1000;h=s['length_m']*500
    theta=np.arange(angular)*2*np.pi/angular;rad=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v
    side=c+np.linspace(-h,h,axial)[:,None,None]*a+r*rad[None,:,:]
    sides=side.reshape(-1,3);caps=[]
    for z in [-h,h]:
        caps.append((c+z*a+np.linspace(0,r,25)[:,None,None]*rad).reshape(-1,3))
    return sides,np.concatenate(caps)

def exposed(shapes,part=0):
    """Discard a child's surface points strictly inside another solid child."""
    result=[]
    for j,s in enumerate(shapes):
        p=surface_samples(s)[part];others=[x for k,x in enumerate(shapes)if k!=j]
        if others:p=p[prior.solid_dist(p,others)>=-1e-6]
        result.append(p)
    return np.concatenate(result)

def point_surface(p,g):
    vals=prior.distances(p,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3))
    return dict(max_mm=float(vals.max()),p99_mm=float(np.quantile(vals,.99)),samples=len(vals))

def main():
    OUT.mkdir(exist_ok=True);previous_path=PREVIOUS/'verification.json';prev=json.loads(previous_path.read_text())
    collision_source=Path(prev['collision_candidate']);visual=Path(prev['visual_candidate'])
    assert scan.digest(collision_source)==prev['collision']['sha256'];assert scan.digest(visual)==prev['visual']['sha256']
    installed=Path(prev['sources']['collision']);d,components,original=scan.load_nodes(installed);_,_,current=scan.load_nodes(collision_source)
    step,faces=read_source_faces();meta_path=step.with_name('native.json');meta=json.loads(meta_path.read_text());assert scan.digest(step)==meta['source_step_sha256']
    # CAD cylinder surfaces are axis/radius evidence, not STEP entity-ID selectors.
    # Each numbered shell is matched to the existing native-shell source owner.
    shapes={};recipes=[]
    for ni,sh,main_face,branch_face in [(30,26,446,460),(37,33,491,496)]:
        assert d['nodes'][ni]['name']==f'native-shell-{sh}'and components[ni]=='technology-core/arm-and-shared'
        c,a=source_axis(faces,main_face,sh,38.5);bc,ba=source_axis(faces,branch_face,sh,37.5)
        p=original[ni].reshape(-1,3);z=(p-c)@a
        if ni==30:
            # Keep nominal barrel and raised collar; a flat end approximates the
            # original oblique crown. The review measures this deliberate loss.
            collar_lo=-815.2-c[1];collar_hi=float(z.max())
            branch_end=float(np.max((p-bc)@ba))
        else:
            collar_lo=float((np.array([-615.407,-933.751,-299.8])-c)@a);collar_hi=float(z.max())
            branch_end=float(np.max((p-bc)@ba))
        # Barrel spans the complete source axial extent; branch begins at the
        # closest intersection with that barrel's line and reaches its source rim.
        t=np.linalg.lstsq(np.column_stack([ba,-a]),c-bc,rcond=None)[0][0]
        shapes[ni]=[interval(c,a,38.5,float(z.min()),float(z.max())),
            interval(c,a,41.,collar_lo,collar_hi),interval(bc,ba,37.5,min(t,branch_end),max(t,branch_end))]
        recipes.append(dict(node=ni,source_shell_ordinal=sh,main_cylinder_face_ordinal=main_face,branch_cylinder_face_ordinal=branch_face,
            definition='nominal cylindrical barrel + raised collar + intersecting perpendicular cylindrical branch',
            deliberate_changes='Bores and side-access openings filled; oblique collar crown becomes flat; fine grooves, screw holes and fillets omitted.'))
    # Tube profiles come from the previously approved visual/collision pass.
    for row in prev['tubes']:
        ni=row['collision_node'];c=np.array(row['center_mm']);a=np.array(row['axis']);profile=row['profile_mm']
        if ni==17:
            sections=[(58.2,profile[0][0],74.91),(66.,74.81,83.),(76.,82.9,profile[-1][0])]
        else:
            sections=[(39.6,profile[0][0],profile[-1][0]),(43.5,profile[0][0],-226.6),(43.5,229.35,profile[-1][0])]
        shapes[ni]=[interval(c,a,r,lo,hi)for r,lo,hi in sections]
        recipes.append(dict(node=ni,source_name=d['nodes'][ni]['name'],definition='three overlapping coaxial cylinders for barrel, flare and collars',
            intervals_radius_lo_hi_mm=sections,deliberate_changes='Tube bore is filled in collision; rounded meridian transitions become small axial steps. Visual remains the approved open profile.'))
    # Diagnostic replacement is complete geometry, while native shapes remain
    # parameter records. Do not count the two representations together.
    replacements={i:np.concatenate([prior.cylinder(s)for s in ss])for i,ss in shapes.items()}
    target=OUT/'collision-tech-core.glb';check=prior.replace(collision_source,target,replacements)
    all_shapes={r['node']:r['cylinders']for r in prev['joints']};all_shapes.update(shapes)
    native_rows=[dict(node_index=i,node_name=d['nodes'][i]['name'],cylinders=ss,review_status='expanded-arm-cylinder-trial-not-contact-approved')for i,ss in all_shapes.items()]
    # Source is original installed collision: this bundle is self-contained and
    # independent of the prior arm recipe's intermediate tube mesh file.
    selection=dict(source_sha256=scan.digest(installed),asset_id='tech-core',replacements=native_rows)
    (OUT/'native-selection.json').write_text(json.dumps(selection,indent=2)+'\n');native=export_native(installed,selection,OUT/'native')
    rows=[]
    for recipe in recipes:
        ni=recipe['node'];ss=shapes[ni];g=original[ni];p=prior.probes(g,30000);sd=prior.solid_dist(p,ss)
        side=exposed(ss);caps=exposed(ss,1)
        rows.append(dict(**recipe,cylinders=ss,original_triangles=len(g),previous_triangles=len(current[ni]),diagnostic_triangles=len(replacements[ni]),
            source_outside_native_union=dict(max_mm=float(max(0,sd.max())),p99_mm=float(max(0,np.quantile(sd,.99))),over_3mm=int((sd>3).sum()),samples=len(sd)),
            exposed_round_sides_to_original=point_surface(side,g),exposed_caps_to_original=point_surface(caps,g),
            cap_caveat='Cap center distances include intentional bore filling. Round-side comparisons exclude faces hidden inside other children, but include the edges of newly filled access openings.'))
    stage_path=PREVIOUS/'paired-stage.json';stage=json.loads(stage_path.read_text());before=copy.deepcopy(stage)
    stage['collision_assets']['tech-core']=dict(path=str(target),sha256=scan.digest(target),triangles=check['after'],placements=2,placed_triangles=2*check['after'])
    mesh_total=sum(x['placed_triangles']for x in stage['collision_assets'].values());stage.update(variant='expanded-core-arm-cylinders',status='expanded arm collision trial; approved visual mapping exact',placed_collision_triangles=mesh_total,installed=False,contact_validated=False)
    (OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
    remaining_arm=sum(len(g)for i,g in original.items()if components[i]=='technology-core/arm-and-shared'and i not in all_shapes)
    pins={str(p):scan.digest(p)for p in [previous_path,collision_source,visual,installed,stage_path,step,meta_path]}
    for p,h in prev['input_pins'].items():assert scan.digest(Path(p))==h;pins[p]=h
    result=dict(source_collision=str(installed),previous_collision=str(collision_source),candidate_collision=str(target),unchanged_visual=str(visual),unchanged_visual_sha256=scan.digest(visual),
        input_pins=pins,source_cylinder_evidence=dict(step=str(step),source_sha256=scan.digest(step),faces=faces,ordinal_caveat='OCCT import ordinals, not original STEP IDs'),
        changed_nodes=sorted(shapes),all_native_nodes=sorted(all_shapes),trials=rows,mesh_check=check,
        additional_placed_preview_saving=(check['before']-check['after'])*2,
        previous_native_cylinders_per_core=prev['native_cylinders_per_core'],native_cylinders_per_core=len(native['native_parts']),
        native_remaining_mesh_triangles_per_core=native['retained_mesh']['triangles'],native_removed_original_mesh_triangles_per_core=native['removed_mesh_triangles'],
        previous_native_arm_mesh_per_core=prev['candidate_arm_collision_triangles_per_core']-prev['native_cylinders_per_core']*96,
        remaining_arm_native_mesh_per_core=remaining_arm,original_arm_mesh_per_core=prev['source_arm_collision_triangles_per_core'],
        field_visual_triangles=stage['placed_visual_triangles'],field_collision_preview_triangles=mesh_total,
        field_native_remaining_mesh_triangles=mesh_total-len(native['native_parts'])*96*2,
        previous_field_collision_preview_triangles=before['placed_collision_triangles'],
        visual_changed=False,installed=False,contact_validated=False,
        caveats=['Overlapping cylinder children stay under their original owner; no cross-owner merge.',
            'Solid tube bores and motor access openings intentionally block routes formerly open in collision.',
            'Flat collar crowns approximate oblique source ends; all deviations are reported, not hidden by bore-fill metrics.',
            'No all-pose clearance, contact, projectile trajectory or runtime performance qualification.'])
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Additional preview saving',result['additional_placed_preview_saving'],'native',result['native_cylinders_per_core'],'per Core; remaining arm mesh',remaining_arm,flush=True)
    for row in rows:print(row['node'],'outside',row['source_outside_native_union'],'side',row['exposed_round_sides_to_original'],'cap',row['exposed_caps_to_original'],flush=True)

if __name__=='__main__':main()
