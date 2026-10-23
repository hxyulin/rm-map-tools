"""Round joint covers and a three-cylinder mounting base; visuals unchanged."""
import copy,importlib.util,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('expanded_arm_previous',ROOT/'benchmarks/2026-10-23-core-arm-cylinders-r2/build.py')
r2=importlib.util.module_from_spec(spec);spec.loader.exec_module(r2)
p=r2.prior;scan=r2.scan
OUT=ROOT/'out/rmuc2027-core-joints-base-r3'
PREVIOUS=ROOT/'out/rmuc2027-core-arm-cylinders-r2'
CAPS={6:2,7:3,12:8,13:9,29:25,34:30,35:31,40:36,41:37,44:40,51:47,53:49,54:50,55:51,56:52}

def main():
    OUT.mkdir(exist_ok=True);previous_path=PREVIOUS/'verification.json';old=json.loads(previous_path.read_text())
    current=Path(old['candidate_collision']);source=Path(old['source_collision']);visual=Path(old['unchanged_visual'])
    assert scan.digest(current)==old['mesh_check']['sha256'];assert scan.digest(visual)==old['unchanged_visual_sha256']
    d,components,nodes=scan.load_nodes(source);_,_,current_nodes=scan.load_nodes(current)
    axis_path=PREVIOUS/'source-cylinders.json';axes=json.loads(axis_path.read_text());shapes={};recipes=[]
    for ni,shell in CAPS.items():
        evidence=next(row for row in axes['cylinders']if row.get('shell')==shell)
        assert d['nodes'][ni]['name']==f'native-shell-{shell}'and components[ni]=='technology-core/arm-and-shared'
        a=np.array(evidence['axis']);c=np.array(evidence['point_mm']);radius=evidence['radius_mm']
        sh=p.extend_to_bounds(p.shape(c,a,radius,1),nodes[ni]);shapes[ni]=[sh]
        recipes.append(dict(node=ni,component=components[ni],source_name=d['nodes'][ni]['name'],definition='one solid source-axis cylinder',
            source_shell_ordinal=shell,source_cylinder_face_ordinal=evidence['face'],nominal_radius_mm=radius,
            deliberate_changes='Ring bore, screw apertures and small surface relief filled; small tabs/fastener details approximated by the cylinder envelope.'))
    # This connector has NURBS source surfaces. Fit circles on the known joint
    # barrel/tube axes; do not infer a new axis or merge independently owned parts.
    research=p.module('joint_connector_circle_fit','benchmarks/2026-10-23-core-arm-proxies/research.py')
    a=np.array([-.342,0,.9397]);a/=np.linalg.norm(a)
    b=np.array([.739856,-.616521,.269286]);b/=np.linalg.norm(b)
    main=research.circles(nodes[27],a)[0];branch=research.circles(nodes[27],b)[0]
    shapes[27]=[p.extend_to_bounds(p.fit_shape(main),nodes[27],58),p.fit_shape(branch)]
    recipes.append(dict(node=27,component=components[27],source_name=d['nodes'][27]['name'],definition='intersecting elbow connector barrel and branch',
        fitted_circle_evidence=[main,branch],deliberate_changes='Connector cavity filled; squared flange corners and fine rim details approximated by round bodies.'))
    rejected_connector=shapes.pop(27);rejected_recipe=recipes.pop()
    # The pedestal's round mounting stack is distinct from the rectangular
    # enclosure. Three cylinders represent sleeve, lower flange and side tab.
    ni=72;g=nodes[ni];pts=np.unique(g.reshape(-1,3),axis=0)
    assert components[ni]=='technology-core/pedestal-and-shoulder'and d['nodes'][ni]['name']=='native-shell-15'
    c=np.array([-100.,0,84.]);a=np.array([0.,1,0]);rad=np.linalg.norm(pts[:,[0,2]]-c[[0,2]],axis=1)
    centers=g.mean(1)
    tab_mask=(centers[:,1]<-430)&(np.linalg.norm(centers[:,[0,2]]-c[[0,2]],axis=1)>80)
    tab=np.unique(g[tab_mask].reshape(-1,3),axis=0);assert len(tab)>=20
    ta=np.array([-.9396926208,0,.3420201433]);ta/=np.linalg.norm(ta);_,u,v=p.basis(ta)
    basis=np.column_stack([u,v,ta]);q=tab@basis;lo,hi=q.min(0),q.max(0);tc=(lo+hi)/2@basis.T
    radius=float(np.linalg.norm(q[:,:2]-(lo[:2]+hi[:2])/2,axis=1).max())
    shapes[72]=[r2.interval(c,a,76.5,float(pts[:,1].min()),-427.5),r2.interval(c,a,109.,-429.6,float(pts[:,1].max())),
        p.shape(tc,ta,radius,float(hi[2]-lo[2]))]
    recipes.append(dict(node=72,component=components[72],source_name=d['nodes'][72]['name'],definition='three-cylinder mounting base: upper sleeve, bottom flange, transverse side tab',
        tab_selection=dict(source_triangle_condition='source triangle centroid Y < -430 mm and distance in XZ from (-100,84) > 80 mm; use all vertices of selected triangles',
            source_triangle_indices=np.flatnonzero(tab_mask).tolist(),count=len(tab),
            bounds_in_tab_basis_mm=[lo.tolist(),hi.tolist()],tab_axis=ta.tolist()),
        deliberate_changes='Main bore filled; tapered sleeve and rounded flange become straight cylinders; rectangular tab becomes a rounded disk with the same thin radial extent.'))
    replacements={i:np.concatenate([p.cylinder(s)for s in ss])for i,ss in shapes.items()}
    target=OUT/'collision-tech-core.glb';check=p.replace(current,target,replacements)
    before_selection=json.loads((PREVIOUS/'native-selection.json').read_text());all_shapes={row['node_index']:row['cylinders']for row in before_selection['replacements']}
    assert not(set(all_shapes)&set(shapes));all_shapes.update(shapes)
    worlds={i:w for i,w,parent in p.scene_nodes(d)}
    for i in all_shapes:assert np.array_equal(worlds[i],np.eye(4))
    selection=dict(source_sha256=scan.digest(source),asset_id='tech-core',replacements=[dict(node_index=i,node_name=d['nodes'][i]['name'],cylinders=ss,
        review_status='joint-and-base-cylinder-trial-not-contact-approved')for i,ss in all_shapes.items()])
    (OUT/'native-selection.json').write_text(json.dumps(selection,indent=2)+'\n');native=p.export_native(source,selection,OUT/'native')
    rows=[]
    for recipe in recipes:
        i=recipe['node'];ss=shapes[i];g=nodes[i];sample=p.probes(g,20000);sd=p.solid_dist(sample,ss)
        rows.append(dict(**recipe,cylinders=ss,previous_triangles=len(current_nodes[i]),diagnostic_triangles=len(replacements[i]),
            source_outside_union=dict(max_mm=float(max(0,sd.max())),p99_mm=float(max(0,np.quantile(sd,.99))),samples=len(sd)),
            exposed_sides_to_source=r2.point_surface(r2.exposed(ss),g),exposed_caps_to_source=r2.point_surface(r2.exposed(ss,1),g)))
    rejected_proxy=np.concatenate([p.cylinder(s)for s in rejected_connector]);rejected_path=OUT/'rejected-elbow-connector.glb'
    p.replace(current,rejected_path,{27:rejected_proxy})
    rejected=dict(**rejected_recipe,cylinders=rejected_connector,path=str(rejected_path),sha256=scan.digest(rejected_path),status='rejected-not-in-stage-or-native-selection',
        exposed_sides_to_source=r2.point_surface(r2.exposed(rejected_connector),nodes[27]),
        reason='Whole-node cylindrical approximation adds unsupported exterior up to 40.23 mm around squared connector/flange; original owner retained.')
    stage_path=PREVIOUS/'paired-stage.json';stage=json.loads(stage_path.read_text());previous_stage=copy.deepcopy(stage)
    stage['collision_assets']['tech-core']=dict(path=str(target),sha256=scan.digest(target),triangles=check['after'],placements=2,placed_triangles=check['after']*2)
    total=sum(entry['placed_triangles']for entry in stage['collision_assets'].values())
    count=len(native['native_parts']);stage.update(variant='core-round-joints-and-three-cylinder-mount',status='additional joint and mounting base collision review; visuals unchanged',
        placed_collision_triangles=total,installed=False,contact_validated=False)
    (OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
    remain={comp:sum(len(g)for i,g in nodes.items()if components[i]==comp and i not in all_shapes)for comp in ['technology-core/arm-and-shared','technology-core/pedestal-and-shoulder']}
    pins={str(x):scan.digest(x)for x in [previous_path,current,source,visual,axis_path,stage_path,PREVIOUS/'native-selection.json']}
    for path,h in old['input_pins'].items():assert scan.digest(Path(path))==h;pins[path]=h
    pedestal_step=ROOT/'out/rmuc2027-equipment-pipeline/technology-core/pedestal-and-shoulder/source.step'
    pedestal_meta=pedestal_step.with_name('native.json');meta=json.loads(pedestal_meta.read_text());assert scan.digest(pedestal_step)==meta['source_step_sha256']
    for x in [pedestal_step,pedestal_meta,OUT/'pedestal-cylinders.json']:pins[str(x)]=scan.digest(x)
    result=dict(source_collision=str(source),previous_collision=str(current),candidate_collision=str(target),unchanged_visual=str(visual),unchanged_visual_sha256=scan.digest(visual),
        changed_nodes=sorted(shapes),all_native_nodes=sorted(all_shapes),trials=rows,rejected_connector=rejected,mesh_check=check,input_pins=pins,
        previous_stage=str(stage_path),previous_field_preview_triangles=previous_stage['placed_collision_triangles'],field_preview_triangles=total,
        field_native_mesh_triangles=total-count*96*2,field_visual_triangles=stage['placed_visual_triangles'],native_cylinders_per_core=count,
        native_remaining_mesh_per_core=native['retained_mesh']['triangles'],remaining_mesh_by_component_per_core=remain,
        additional_original_mesh_removed_per_core=sum(len(nodes[i])for i in shapes),additional_native_cylinders_per_core=sum(len(ss)for ss in shapes.values()),
        additional_placed_preview_saving=2*(check['before']-check['after']),visual_changed=False,installed=False,contact_validated=False,
        caveats=['All ring and mounting bores become solid collision; approved visual openings remain.',
            'Each source owner stays separate. Thin covers remain separate native leaves; no hidden cross-owner removal.',
            'Mounting tab and squared elbow flange are deliberately rounded approximations; inspect local deviation figures and views.',
            'The rectangular pedestal enclosure and the protected head remain unchanged. No contact, all-pose or runtime speed validation.'])
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Native/Core',count,'mesh remainder',result['native_remaining_mesh_per_core'],'component remainder',remain,'additional native removed',result['additional_original_mesh_removed_per_core']*2,flush=True)
    for row in rows:print(row['node'],'outside',round(row['source_outside_union']['max_mm'],3),'side',round(row['exposed_sides_to_source']['max_mm'],3),'cap',round(row['exposed_caps_to_source']['max_mm'],3),flush=True)

if __name__=='__main__':main()
