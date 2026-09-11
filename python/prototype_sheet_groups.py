#!/usr/bin/env python3
"""Prototype one repeated sheet group as a shared AP214 assembly definition.

Produces isolated baseline/candidate STEP files, source identity sidecars,
OCCT validation, and tar.zst measurements. Does not modify production exports.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

import numpy as np
import provenance
from scipy.spatial import cKDTree
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from OCP.TDF import TDF_Label
from OCP.Quantity import Quantity_Color
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf, XCAFDoc_ColorGen
from OCP.collections import Sequence_TDF_Label
from OCP.TopoDS import TopoDS
from audit_geometry import bounds, compound, shape_map
from audit_geometry_duplicates import GeometryFingerprints
from export_step_elements import Assembly, p21_string
from p21index import Index
from p21model import Model, first_string
from p21split import Splitter, forward_closure
from validate_parts import analyse, read_part, colour_key


def select_orbits(groups, product, seed_index=0):
    seed=groups[seed_index]
    if seed['type']!='SHELL_BASED_SURFACE_MODEL' or any(body['products']!=[product] for body in seed['bodies']):
        raise ValueError('seed must contain only sheet bodies owned by the selected product')
    placements=np.array([b['reference_to_body_matrix_mm'] for b in seed['bodies']])
    for matrix in placements:
        rotation=matrix[:3,:3]
        if (matrix.shape!=(4,4) or not np.isfinite(matrix).all()
                or not np.allclose(matrix[3],[0,0,0,1],atol=1e-9)
                or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-7)
                or np.linalg.det(rotation)<=0):
            raise ValueError('seed placements must be proper rigid transforms')
    placements[0]=np.eye(4)
    selected=[]; used=set()
    for group in groups:
        if group['type']!='SHELL_BASED_SURFACE_MODEL': continue
        bodies=[b for b in group['bodies'] if b['products']==[product]]
        if len(bodies)<len(placements): continue
        transforms=np.array([b['reference_to_body_matrix_mm'] for b in bodies])
        for j,body in enumerate(bodies):
            if body['id'] in used: continue
            expected=placements@transforms[j]
            delta=np.abs(expected[:,None,:,:]-transforms[None,:,:,:])
            good=(delta[:,:,:3,:3].max(axis=(2,3))<1e-7)&(delta[:,:,:3,3].max(axis=2)<1e-3)
            if not np.all(good.sum(axis=1)==1): continue
            indices=good.argmax(axis=1)
            if len(set(indices))!=len(indices): continue
            ids=[bodies[i]['id'] for i in indices]
            if used.intersection(ids): continue
            selected.append(dict(reference_body=body['id'],instance_bodies=ids,
                                 geometry_entities=group['representative_geometry_entities']))
            used.update(ids)
    return placements,selected


def face_styles(ix,model,fingerprints,body):
    result=[]
    for face,shell in model.body_faces_shells(body):
        style=None
        for target in [face,shell,body]:
            rows=model.style_of_target.get(target,[])
            if rows:
                style=[]
                for row in rows:
                    refs=ix.refs_of(row)
                    assignments=refs[:-2] if ix.tname(row)=='OVER_RIDING_STYLED_ITEM' else refs[:-1]
                    style.append(tuple(fingerprints.signature(ix.r(int(ref))).hex() for ref in assignments))
                break
        result.append(style)
    return result


def area(shape):
    properties=GProp_GProps(); BRepGProp.SurfaceProperties_s(shape,properties)
    return abs(properties.Mass())


def face_records(doc):
    """Read colours on definitions before applying each XDE occurrence location."""
    st=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct=XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    result=[];definitions=[];definition_faces=0
    col=Quantity_Color()
    def colour(item):
        return colour_key(col) if ct.GetColor(item,XCAFDoc_ColorSurf,col) or ct.GetColor(item,XCAFDoc_ColorGen,col) else None
    def walk(label,location):
        nonlocal definition_faces
        referred=TDF_Label()
        if st.GetReferredShape_s(label,referred):
            walk(referred,location.Multiplied(st.GetLocation_s(label)))
            return
        if st.IsAssembly_s(label):
            components=Sequence_TDF_Label();st.GetComponents_s(label,components)
            for i in range(1,components.Length()+1):walk(components.Value(i),location)
            return
        shape=st.GetShape_s(label)
        faces=shape_map(shape,TopAbs_FACE)
        if not any(label.IsEqual(old) for old in definitions):
            definitions.append(label);definition_faces+=faces.Extent()
        inherited={}
        for kind in [TopAbs_SHELL,TopAbs_SOLID]:
            bodies=shape_map(shape,kind)
            for i in range(1,bodies.Extent()+1):
                body=bodies.FindKey(i);value=colour(body)
                if value is None:continue
                owned=shape_map(body,TopAbs_FACE)
                for j in range(1,owned.Extent()+1):
                    inherited.setdefault(faces.FindIndex(owned.FindKey(j)),value)
        root_colour=colour(shape)
        for i in range(1,faces.Extent()+1):
            original=faces.FindKey(i)
            value=colour(original) or inherited.get(i) or root_colour
            face=TopoDS.Face(original.Moved(location));properties=GProp_GProps()
            BRepGProp.SurfaceProperties_s(face,properties)
            centre=properties.CentreOfMass()
            result.append(dict(shape=face,colour=value,centre=np.array([centre.X(),centre.Y(),centre.Z()]),
                               area=abs(properties.Mass()),bounds=np.array(bounds(face))))
    roots=Sequence_TDF_Label();st.GetFreeShapes(roots)
    for i in range(1,roots.Length()+1):walk(roots.Value(i),TopLoc_Location())
    return result,dict(unique_leaf_definitions=len(definitions),stored_faces=definition_faces)


def compare_documents(before,after,booleans=True):
    baseline,candidate=compound(before),compound(after)
    left,before_storage=face_records(before)
    right,after_storage=face_records(after)
    if len(left)!=len(right): raise ValueError('face count changed')
    centres=np.array([record['centre'] for record in left]);tree=cKDTree(centres)
    used=set();mapping=[];distance=[]
    for new in right:
        candidates=tree.query_ball_point(new['centre'],1e-5)
        possible=[i for i in candidates if i not in used
            and left[i]['colour']==new['colour']
            and np.abs(left[i]['bounds']-new['bounds']).max()<=1e-5
            and abs(left[i]['area']-new['area'])<=max(1e-8,left[i]['area']*1e-7)]
        if not possible:raise ValueError('no unused corresponding face with matching geometry and colour')
        index=min(possible,key=lambda i:np.linalg.norm(centres[i]-new['centre']))
        used.add(index);mapping.append(index);distance.append(np.linalg.norm(centres[index]-new['centre']))
    distance=np.array(distance)
    max_box=0.; max_area=0.; max_remainder=0.
    for new,index in zip(right,mapping):
        old=left[index]
        if old['colour']!=new['colour']:raise ValueError('imported face colour changed')
        box_delta=float(np.abs(new['bounds']-old['bounds']).max())
        area_delta=abs(new['area']-old['area'])
        max_box=max(max_box,box_delta);max_area=max(max_area,area_delta)
        if box_delta>1e-5 or area_delta>max(1e-8,old['area']*1e-7):
            raise ValueError(f'face geometry changed: bbox {box_delta} mm, area {area_delta} mm2')
        for a,b in ([(old['shape'],new['shape']),(new['shape'],old['shape'])] if booleans else []):
            cut=BRepAlgoAPI_Cut(a,b);cut.Build()
            if not cut.IsDone(): raise ValueError('face boolean comparison failed')
            remainder=area(cut.Shape());max_remainder=max(max_remainder,remainder)
            if remainder>max(1e-8,old['area']*1e-7):
                raise ValueError(f'face subtraction left {remainder} mm2')
    valid=[bool(BRepCheck_Analyzer(shape).IsValid()) for shape in [baseline,candidate]]
    if not all(valid): raise ValueError('invalid imported shape')
    return dict(faces_checked=len(left),all_shapes_valid=True,
        face_colours=dict(Counter(record['colour'] for record in left)),
        per_face_colours_match=True,baseline_storage=before_storage,shared_storage=after_storage,
        max_face_centroid_delta_mm=float(distance.max()),max_face_bbox_delta_mm=max_box,
        max_face_area_delta_mm2=max_area,max_bidirectional_cut_area_mm2=max_remainder if booleans else None,
        boolean_face_pairs_checked=len(left) if booleans else 0,
        baseline_import=analyse(before),candidate_import=analyse(after))


def prototype_header(ix,path,checksum):
    return provenance.step_header(ix.header,path.name,'prototype_sheet_groups.py',ix.source,checksum,
        'Experimental repeated-sheet grouping comparison; shared occurrences use identity-map.json for original body identities')


def write_whole_product(ix,model,splitter,product,orbits,placements,output,source_sha256):
    """Keep the remainder intact and add one shared sheet definition plus placements."""
    selected={eid for orbit in orbits for eid in orbit['instance_bodies']}
    reference={orbit['reference_body'] for orbit in orbits}
    bodies={int(ix.ids[body]) for body,rep in model.bodies if model.rep_product.get(rep)==product}
    if not selected <= bodies: raise ValueError('selection is outside the source product')
    baseline=output/'baseline-product.step';shared=output/'shared-product.step'
    mask,rewritten=splitter.closure_products([product])
    splitter.write_closure(mask,rewritten,str(baseline),header=prototype_header(ix,baseline,source_sha256))
    mask,rewritten=splitter.closure_products([product],body_ids=(bodies-selected)|reference)
    _,remainder_rewritten=splitter.closure_products([product],body_ids=bodies-selected)
    # Retain the reference geometry/styles, but remove it from the remainder's representation.
    for rep in model.product_reps[product]:
        if rep in remainder_rewritten: rewritten[rep]=remainder_rewritten[rep]
    asm=Assembly(ix,model,ix.max_id+1)
    original_sr=asm.sr_of[product]
    context=asm.last_ref(original_sr)
    product_context=asm.last_ref(product);pd_context=asm.last_ref(asm.pd_of[product])
    def new_product(name,sr):
        pr=asm.add(f"PRODUCT({p21_string(name)},{p21_string(name)},$,(#{product_context}))")
        pdf=asm.add(f"PRODUCT_DEFINITION_FORMATION('',$,#{pr})")
        pd=asm.add(f"PRODUCT_DEFINITION('','',#{pdf},#{pd_context})")
        pds=asm.add(f"PRODUCT_DEFINITION_SHAPE('',$,#{pd})")
        asm.add(f"SHAPE_DEFINITION_REPRESENTATION(#{pds},#{sr})")
        return pd
    group_axis=asm.axis(np.eye(4))
    refs=','.join(f'#{eid}' for eid in [group_axis]+sorted(reference))
    group_sr=asm.add(f"MANIFOLD_SURFACE_SHAPE_REPRESENTATION('shared sheets',({refs}),#{context})")
    group_pd=new_product('prototype-shared-sheet-group',group_sr)
    original_axis,original_frame=asm.child_axis(original_sr)
    if original_axis is None: original_axis=asm.axis(np.eye(4))
    leaves=[(int(ix.ids[asm.pd_of[product]]),int(ix.ids[original_sr]),original_axis,original_frame,'remaining-source-bodies')]
    leaves += [(group_pd,group_sr,group_axis,m,f'sheet-group:{i}') for i,m in enumerate(placements)]
    root_axis=asm.axis(np.eye(4));axes=[asm.axis(item[3]) for item in leaves]
    refs=','.join(f'#{eid}' for eid in [root_axis]+axes)
    root_sr=asm.add(f"SHAPE_REPRESENTATION('',({refs}),#{context})")
    root_pd=new_product('prototype-grouped-'+model.pname(product),root_sr)
    for (child_pd,child_sr,child_axis,_,name),axis in zip(leaves,axes):
        text=p21_string(name)
        occ=asm.add(f"NEXT_ASSEMBLY_USAGE_OCCURRENCE({text},{text},{text},#{root_pd},#{child_pd},{text})")
        shape=asm.add(f"PRODUCT_DEFINITION_SHAPE('',$,#{occ})")
        transform=asm.add(f"ITEM_DEFINED_TRANSFORMATION($,$,#{child_axis},#{axis})")
        relation=asm.add(f"(REPRESENTATION_RELATIONSHIP($,$,#{child_sr},#{root_sr}) REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#{transform}) SHAPE_REPRESENTATION_RELATIONSHIP())")
        asm.add(f"CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#{relation},#{shape})")
    rest_rows=[ix.r(eid) for eid in bodies-selected]
    geometry=forward_closure(ix,rest_rows,np.zeros(ix.n,dtype=bool))
    if not mask[geometry].all() or any(geometry[row] for row in rewritten):
        raise ValueError('remainder geometry would be removed or rewritten')
    splitter.write_closure(mask,rewritten,str(shared),extra=asm.entities,header=prototype_header(ix,shared,source_sha256))
    unchanged=dict(geometry_records=int(geometry.sum()),copied_without_rewriting=True)
    return baseline,shared,len(bodies),unchanged


def compress_and_verify(path,sidecar=None):
    tar_path=path.with_suffix('.tar');archive=path.with_suffix('.tar.zst')
    members=[(path,'model.step')]+([(sidecar,'identity-map.json')] if sidecar else [])
    with tarfile.open(tar_path,'w',format=tarfile.USTAR_FORMAT) as tar:
        for source,name in members:
            info=tar.gettarinfo(str(source),arcname=name)
            info.uid=info.gid=info.mtime=0;info.uname=info.gname='';info.mode=0o644
            with source.open('rb') as f:tar.addfile(info,f)
    start=time.perf_counter()
    subprocess.run(['zstd','-9','-T1','--no-progress',str(tar_path),'-o',str(archive)],check=True)
    elapsed=time.perf_counter()-start
    data=subprocess.check_output(['zstd','-dc',str(archive)])
    import io
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as tar:
        if tar.getnames()!=[name for _,name in members]:raise ValueError('unexpected archive members')
        for source,name in members:
            actual=hashlib.sha256(tar.extractfile(name).read()).hexdigest()
            if actual!=hashlib.sha256(source.read_bytes()).hexdigest():raise ValueError('archive checksum mismatch')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    tar_path.unlink()
    return dict(step_bytes=path.stat().st_size,sidecar_bytes=sidecar.stat().st_size if sidecar else 0,tar_zstd_bytes=archive.stat().st_size,
                compression_seconds=elapsed,sha256=digest,archive_verified=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('index',type=Path);ap.add_argument('candidates',type=Path)
    ap.add_argument('--product',default='001_1_ASM')
    ap.add_argument('--seed-index',type=int,default=0)
    ap.add_argument('--whole-product',action='store_true')
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    report=json.loads(args.candidates.read_text())
    placements,orbits=select_orbits(report['matches'],args.product,args.seed_index)
    if not orbits or len(placements)<2:raise ValueError('no repeated sheet group')
    ix=Index(args.index)
    try:
        checksum=hashlib.sha256(ix.mm).hexdigest()
        if checksum!=report['source_sha256']:raise ValueError('source checksum mismatch')
        model=Model(ix);splitter=Splitter(ix,model);fingerprints=GeometryFingerprints(ix)
        products=[row for row in model.product_name if model.pname(row)==args.product]
        if len(products)!=1:raise ValueError('product name is not unique')
        product=products[0]
        kept=[];rejected=[]
        for orbit in orbits:
            styles=[face_styles(ix,model,fingerprints,ix.r(eid)) for eid in orbit['instance_bodies']]
            if any(style!=styles[0] for style in styles):
                rejected.append(orbit);continue
            orbit['source_body_names']=[first_string(ix.args(ix.r(eid))) for eid in orbit['instance_bodies']]
            kept.append(orbit)
        if not kept:raise ValueError('no groups preserve styles')
        all_ids={eid for orbit in kept for eid in orbit['instance_bodies']}
        reference_ids={orbit['reference_body'] for orbit in kept}
        selection=dict(source=ix.source,source_sha256=checksum,product=args.product,
                       placements_mm=placements.tolist(),orbits=kept,rejected_style_orbits=rejected,
                       occurrence_names=dict(isolated=[f'{args.product}:{i}' for i in range(len(placements))],
                                             whole_product=[f'sheet-group:{i}' for i in range(len(placements))]),
                       identity_mapping='Each column of instance_bodies/source_body_names corresponds to one placement; shared STEP bodies retain reference names.')
        (args.out/'selection.json').write_text(json.dumps(selection,indent=2)+'\n')
        paths=[args.out/'baseline.step',args.out/'shared.step']; docs=[]; readers=[]
        for path,ids,shared in [(paths[0],all_ids,False),(paths[1],reference_ids,True)]:
            mask,rewritten=splitter.closure_products([product],body_ids=ids)
            extra=[]
            if shared:
                asm=Assembly(ix,model,ix.max_id+1)
                extra=asm.build('repeated-sheet-group',f'{len(placements)} placements of a shared sheet group',[(product,m) for m in placements])
            splitter.write_closure(mask,rewritten,str(path),extra=extra,header=prototype_header(ix,path,checksum))
            doc,reader,error=read_part(str(path))
            if error:raise ValueError(error)
            docs.append(doc);readers.append(reader)
        validation=compare_documents(*docs)
        result=dict(source_sha256=checksum,prototype_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),product=args.product,placements=len(placements),
                    baseline_body_definitions=len(all_ids),shared_body_definitions=len(reference_ids),
                    rejected_style_orbits=len(rejected),validation=validation,
                    baseline=compress_and_verify(paths[0]),shared=compress_and_verify(paths[1],args.out/'selection.json'))
        if args.whole_product:
            before_path,after_path,body_count,unchanged=write_whole_product(ix,model,splitter,product,kept,placements,args.out,checksum)
            full_docs=[]
            for path in [before_path,after_path]:
                doc,reader,error=read_part(str(path))
                if error:raise ValueError(error)
                full_docs.append(doc);readers.append(reader)
            result['whole_product']=dict(baseline_bodies=body_count,
                candidate_bodies=body_count-len(all_ids)+len(reference_ids),
                unchanged_remainder=unchanged,
                validation=compare_documents(*full_docs,booleans=False),
                baseline=compress_and_verify(before_path),shared=compress_and_verify(after_path,args.out/'selection.json'))
        (args.out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)
    finally:
        ix.mm.close();ix._f.close()

if __name__=='__main__':main()
