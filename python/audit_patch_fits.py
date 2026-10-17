#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Discover finite patch reuse and measured primitive-fit opportunities in STEP."""
import argparse
from collections import Counter,defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from cad_document import CadDocument
from cad_patch_matching import polygon_patch,patch_key,patch_correspondence,PATCH_CONTRACT
from cad_shape_fitting import bspline_samples,polygon_fits,fit_round_profiles,fit_wave_profiles,native_spline_sample_error,FIT_CONTRACT


BUDGETS=(1e-6,.01,.1,.5,1.,5.)


def face_edges(ix,face):
    refs=ix.refs_of(ix.r(face))
    for bound in refs[:-1]:
        for loop in ix.refs_of(ix.r(int(bound))):
            if ix.tname(ix.r(int(loop)))!='EDGE_LOOP':continue
            for use in ix.refs_of(ix.r(int(loop))):
                ref=ix.refs_of(ix.r(int(use)))
                if len(ref)==1 and ix.tname(ix.r(int(ref[0])))=='EDGE_CURVE':yield int(ref[0])


def audit(source,output,*,hierarchy=None,curve_limit=24):
    if output.exists():raise FileExistsError(output)
    if curve_limit<0:raise ValueError('negative curve limit')
    started=time.perf_counter();skips=Counter();exact_skips=Counter();sizes=Counter()
    exact={};near={};proposals=[];counts=defaultdict(Counter);unique_counts=defaultdict(Counter);curves=[];curve_skips=Counter()
    with CadDocument.from_step(source,workers=1,intern_layers=True) as doc:
        if set(doc.geometry_length_units)!={'.MILLI.,.METRE.'}:raise ValueError('audit thresholds require explicit millimetre source geometry')
        catalog=json.loads(hierarchy.read_text()) if hierarchy else None
        if catalog and catalog.get('files_sha256',{}).get('field.step')!=doc.source_sha256:raise ValueError('hierarchy source mismatch')
        component_by_body={}
        for component in catalog['components'] if catalog else []:
            for body in component['export_body_ids'].values():component_by_body[int(body)]=component['id']
        ix=doc.index;face_owners=defaultdict(set)
        for body,_ in doc.model.bodies:
            body_id=int(ix.ids[body]);component=component_by_body.get(body_id,'body/'+str(body_id))
            for face in doc.model.body_faces(body):face_owners[int(ix.ids[face])].add(component)
        faces=sorted(face_owners);edge_owner=defaultdict(set)
        for face in faces:
            for edge in face_edges(ix,face):edge_owner[edge].update(face_owners[face])
        print('source loaded:',len(faces),'faces',flush=True)
        for index,face in enumerate(faces):
            try:patch=polygon_patch(doc,face)
            except ValueError as error:skips[str(error)]+=1;continue
            sizes[len(patch.points)]+=1
            key,full,order=patch_key(patch,quantum=.01)
            if key not in near:near[key]={'key':full,'faces':[]}
            if near[key]['key']!=full:raise ValueError('discovery digest collision')
            near[key]['faces'].append(face)
            try:
                key,full,order=patch_key(patch)
                if key not in exact:exact[key]={'key':full,'faces':[]}
                if exact[key]['key']!=full:raise ValueError('exact digest collision')
                exact[key]['faces'].append(face)
            except ValueError as error:exact_skips[str(error)]+=1
            try:fit=polygon_fits(patch.coordinates(),tolerance=.1)
            except ValueError as error:skips['fit: '+str(error)]+=1;continue
            best_errors={}
            for model in fit['models']:
                kind=model['model'];error=model['continuous_boundary_error_bound_source_units']
                best_errors[kind]=min(best_errors.get(kind,float('inf')),error)
                counts[kind]['inspected']+=1
                for budget in BUDGETS:
                    if error<=budget:counts[kind][str(budget)]+=1
                if error<=.5 and (len(patch.points)>len(model['corners']) or error>1e-6):
                    proposals.append({'source_face_id':face,'components':sorted(face_owners[face]),
                        'source_bbox_mm':[patch.coordinates().min(axis=0).tolist(),patch.coordinates().max(axis=0).tolist()],
                        'original_edges':len(patch.points),'simplification':fit['simplification'],'fit':model})
            for kind,error in best_errors.items():
                unique_counts[kind]['inspected']+=1
                for budget in BUDGETS:
                    if error<=budget:unique_counts[kind][str(budget)]+=1
            if index%10000==0:print('patches:',index,'/',len(faces),flush=True)
        print('polygon audit ready',flush=True)
        def groups(table,quantum):
            selected=sorted((entry for entry in table.values() if len(entry['faces'])>1),key=lambda item:-len(item['faces']))
            examples=[]
            for entry in selected[:20]:
                members=entry['faces'];first=polygon_patch(doc,members[0]);second=polygon_patch(doc,members[1])
                examples.append({'members':len(members),'source_face_ids_first_16':members[:16],
                                 'components':sorted({name for face in members for name in face_owners[face]}),
                                 'example_correspondence':patch_correspondence(first,second,quantum=quantum)})
            return {'groups':len(selected),'additional_face_uses':sum(len(item['faces'])-1 for item in selected),
                    'examples_first_20':examples,'scope':'finite single-loop planar polygons only; no material/ownership merge or mesh reuse applied'}
        exact_report=groups(exact,None);near_report=groups(near,.01)
        # Budgeted representative spline sampling; long road curves first, then
        # other longest source edges. Both classes retain exact source locators.
        candidates=[]
        for row in ix.rows_of('EDGE_CURVE'):
            refs=list(map(int,ix.refs_of(int(row))))
            if len(refs)!=3 or ix.tname(ix.r(refs[2]))!='B_SPLINE_CURVE_WITH_KNOTS':continue
            edge=int(ix.ids[row]);owners=sorted(edge_owner.get(edge,()))
            try:samples=bspline_samples(doc,edge,17)
            except ValueError as error:curve_skips[str(error)]+=1;continue
            span=float(np.linalg.norm(np.ptp(samples,axis=0)))
            centered=samples-samples.mean(axis=0);_,_,basis=np.linalg.svd(centered,full_matrices=False)
            line_error=float(np.linalg.norm(centered@basis[1:].T,axis=1).max())
            candidates.append((edge,owners,span,line_error))
        road=sorted((c for c in candidates if any('road-surface' in name for name in c[1])),key=lambda item:-item[2])
        other=sorted((c for c in candidates if c not in road),key=lambda item:-item[2])
        road_selected=road[:curve_limit//2]
        budget=curve_limit-len(road_selected)
        curved=[c for c in other if c[3]>.01]
        flat=[c for c in other if c[3]<=.01]
        # Include genuinely curved examples, rather than spending the whole
        # non-road budget on the longest almost-straight spline edges.
        other_selected=curved[:max(0,budget-budget//3)]+flat[:budget//3]
        used={c[0] for c in other_selected}
        other_selected += [c for c in other if c[0] not in used][:budget-len(other_selected)]
        selected=road_selected+other_selected
        print('spline inventory:',len(candidates),'selected:',len(selected),'road:',len(road),flush=True)
        for edge,owners,span,line_error in selected:
            training=bspline_samples(doc,edge,129);validation=bspline_samples(doc,edge,2049)
            native_error=native_spline_sample_error(doc,edge,validation)
            try:models=fit_round_profiles(training,validation)+fit_wave_profiles(training,validation)
            except (ValueError,np.linalg.LinAlgError,FloatingPointError) as error:curve_skips[type(error).__name__+': '+str(error)]+=1;continue
            models.sort(key=lambda model:model['max_sample_error_source_units'])
            complexity={'line':0,'circle':1,'ellipse':2,'sinusoid':3,'semiellipse_train':4}
            preferred={str(budget):next((m['model'] for m in sorted(models,key=lambda model:complexity[model['model']])
                       if m['max_sample_error_source_units']<=budget),None) for budget in (.01,.1,.5)}
            curves.append({'source_edge_id':edge,'components':owners,'span_mm':span,
                           'source_bbox_mm':[validation.min(axis=0).tolist(),validation.max(axis=0).tolist()],
                           'native_source_evaluation_max_error_mm':native_error,'training_samples':129,'validation_samples':2049,'profile_samples_mm':training.tolist(),
                           'simplest_model_within_sample_error_mm':preferred,'models':models})
            print('curve:',edge,owners[:1],models[0]['model'],models[0]['max_sample_error_source_units'],flush=True)
        # Prefer proposals reducing segmentation, then small errors. Keep findings
        # compact and explicitly report truncation rather than silently dropping it.
        proposals.sort(key=lambda item:(-(item['original_edges']-len(item['fit']['corners'])),item['fit']['continuous_boundary_error_bound_source_units']))
        doc.verify_source()
        report={'_license':'MIT OR Apache-2.0','_copyright':'Copyright (c) 2026 hxyulin <hxyulin@proton.me>',
                'contracts':[asdict(PATCH_CONTRACT),asdict(FIT_CONTRACT)],'schema_version':1,'source_sha256':doc.source_sha256,'source_units':'mm',
                'source_faces':len(faces),'supported_polygon_faces':sum(sizes.values()),'polygon_edge_counts':dict(sizes),
                'polygon_skips':dict(skips),'exact_incidence_skips':dict(exact_skips),
                'exact_finite_patch_groups':exact_report,'quantized_patch_candidates_0_01mm':near_report,
                'polygon_fit_evaluations_within_mm':dict(counts),'polygon_fit_unique_faces_within_mm':dict(unique_counts),'polygon_proposals_within_0_5mm':len(proposals),
                'polygon_examples_first_40':proposals[:40],
                'spline_edges_full_span_supported':len(candidates),'road_spline_edges':len(road),
                'spline_line_candidates_within_0_01mm_at_17_samples':sum(c[3]<=.01 for c in candidates),
                'spline_edges_fitted':len(curves),'curve_limit':curve_limit,'spline_skips':dict(curve_skips),
                'curve_examples':curves,'source_unchanged':True,'elapsed_seconds':time.perf_counter()-started,
                'scope':'read-only finite-polygon congruence and approximate-fit proposals; sampled curve errors are not continuous certificates; no CAD, mesh or runtime edits',
                'producer_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in ('cad_patch_matching.py','cad_shape_fitting.py','audit_patch_fits.py')}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--hierarchy',type=Path)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--curve-limit',type=int,default=24)
    args=parser.parse_args();audit(args.source,args.out,hierarchy=args.hierarchy,curve_limit=args.curve_limit)
