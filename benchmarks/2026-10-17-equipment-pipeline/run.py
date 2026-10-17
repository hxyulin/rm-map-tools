#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Inventory the complete hierarchy and trial reusable passes on other equipment.

Source geometry and appearance remain DJI / RoboMaster property. Generated
candidates are visual inspection artifacts, not installed runtime assets.
"""
import argparse, collections, gc, json, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_document import CadDocument
from cad_wall_fill import shape_map
from cad_local_lod import guarded_vertex_lod, planar_outline_vertices
from cad_planar_shell import planar_skin
from export_field_package import GlbWriter
from mesh_parts import tessellate
from mesh_quality import deviation
from p21split import Splitter
from plan_cad_lods import build_plan,digest
from validate_parts import read_part
from OCP.TopAbs import TopAbs_FACE,TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def save_mesh(folder,stage,p,t,m,palette,units):
    np.savez(folder/(stage+'.npz'),positions_mm=p,triangles=t,material_ids=m,unit_ids=units,palette=np.array([v or '' for v in palette]))
    writer=GlbWriter(stage,{'version':'2.0','copyright':'DJI / RoboMaster source geometry and appearance; inspection candidate'})
    for unit in np.unique(units):
        ids=np.flatnonzero(units==unit);used,inv=np.unique(t[ids],return_inverse=True)
        writer.add_node('native-shell-'+str(unit),p[used]/1000,inv.reshape(-1,3),[palette[k] for k in m[ids]],extras={'native_shell_index':int(unit),'inspection_only':True})
    writer.write(folder/(stage+'.glb'))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--optimize',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';source=hp.with_name('field.step');h=json.loads(hp.read_bytes());uses=collections.Counter(n['component_id'] for n in build_plan(h)['nodes'] if n['component_id'])
    terrain=json.loads((ROOT/'out/rmuc2027-terrain-density/summary.json').read_bytes())
    # The established 74-definition terrain scope is pinned independently below.
    terrain_ids={c['id'] for c in json.loads((ROOT/'out/rmuc2027-terrain-cost-full/audit.json').read_bytes())['components']}
    terrain_ids|={'under-highland-fan-grille/body-2615732','tunnel-fan-grille/body-2624811'}
    rows=[];start=time.perf_counter()
    if not a.optimize:
        if digest(source)!=h['files_sha256']['field.step']:raise ValueError('hierarchy source changed')
        with CadDocument.from_step(source,workers=1,intern_layers=True) as cad:
            splitter=Splitter(cad.index,cad.model)
            for component in h['components']:
                cid=component['id'];folder=a.out/cid;folder.mkdir(parents=True,exist_ok=True);record=folder/'native.json'
                if record.exists():
                    r=json.loads(record.read_bytes())
                    if r['hierarchy_sha256']!=digest(hp):raise ValueError('stale inventory')
                    rows.append(r);continue
                mask,rewrite=splitter.closure_products([cad.index.r(component['export_product_id'])]);splitter.write_closure(mask,rewrite,folder/'source.step')
                doc,reader,error=read_part(str(folder/'source.step'))
                if error:raise ValueError(error)
                labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels)
                if labels.Length()!=1:raise ValueError('expected one work-part root')
                shape=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));faces=shape_map(shape,TopAbs_FACE);shells=shape_map(shape,TopAbs_SHELL);owner={}
                for j in range(1,shells.Extent()+1):
                    local=shape_map(shells.FindKey(j),TopAbs_FACE)
                    for k in range(1,local.Extent()+1):
                        index=faces.FindIndex(local.FindKey(k))
                        if index in owner:raise ValueError('shared shell face ownership')
                        owner[index]=j
                counts=[];stats={}
                p,t,m,palette=tessellate(doc,.4,.25,stats,lambda i,f,n:counts.extend([owner.get(faces.FindIndex(f),-faces.FindIndex(f))]*n))
                if faces.Extent()!=component['face_count'] or stats.get('unmeshed_faces') or len(counts)!=len(t):raise ValueError('incomplete native tessellation')
                selected=cid not in terrain_ids and cid!='base/source-model'
                if selected:save_mesh(folder,'native',p,t,m,palette,np.array(counts))
                r={'id':cid,'source_product_id':component['source_product_id'],'source_faces':faces.Extent(),'shells':shells.Extent(),'uses':uses[cid],'native_triangles':len(t),'selected':selected,'hierarchy_sha256':digest(hp),'source_step_sha256':digest(folder/'source.step'),'stats':stats}
                if selected:r['native_npz_sha256']=digest(folder/'native.npz');r['native_glb_sha256']=digest(folder/'native.glb')
                record.write_text(json.dumps(r,indent=2)+'\n');rows.append(r);print(cid,len(t),'x',uses[cid],flush=True)
                del doc,reader,shape,faces,shells,p,t,m;gc.collect()
            cad.verify_source()
    else:
        inventory=json.loads((a.out/'inventory.json').read_bytes())
        if inventory['hierarchy_sha256']!=digest(hp):raise ValueError('hierarchy changed')
        for native in inventory['components']:
            if not native['selected']:continue
            cid=native['id'];folder=a.out/cid
            if (folder/'passes.json').exists():rows.append(json.loads((folder/'passes.json').read_bytes()));continue
            if digest(folder/'native.npz')!=native['native_npz_sha256'] or digest(folder/'source.step')!=native['source_step_sha256']:raise ValueError('native input changed')
            d=np.load(folder/'native.npz');p=d['positions_mm'];t=d['triangles'];m=d['material_ids'];u=d['unit_ids'];palette=[v or None for v in d['palette'].tolist()]
            protected=[i for i,c in enumerate(palette) if c is None or np.ptp(list(map(float,c.split(','))))>.1]
            doc,reader,error=read_part(str(folder/'source.step'))
            if error:raise ValueError(error)
            labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);shape=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));shells=shape_map(shape,TopAbs_SHELL)
            chunks={'planar':[],'lod':[]};proofs=[]
            for unit in np.unique(u):
                ids=np.flatnonzero(u==unit);used,inv=np.unique(t[ids],return_inverse=True);pp=p[used];tt=inv.reshape(-1,3);mm=m[ids]
                if len(tt)>=128:
                    p1,t1,m1,skin=planar_skin(pp,tt,mm,protected_material_ids=protected)
                    locks=set(np.unique(t1[np.isin(m1,protected)]).tolist())
                    if unit>0:
                        from scipy.spatial import cKDTree
                        outline,_=planar_outline_vertices(shells.FindKey(int(unit)),minimum_face_area_mm2=5000,corner_turn_rad=0)
                        if len(outline):
                            distances,nearest=cKDTree(p1).query(outline);locks.update(map(int,nearest[distances<=.01]))
                            for v in outline[distances>.01]:locks.update(map(int,np.atleast_1d(cKDTree(p1).query(v,k=min(8,len(p1)))[1])))
                    p2,t2,m2,lod=guarded_vertex_lod(p1,t1,m1,error_mm=.25,sampled_limit_mm=1,sample_count=8192,maximum_iterations=8,protected_vertex_indices=np.array(sorted(locks),dtype=np.int64))
                    # The reducer's shared float32 frame also rounds locked
                    # vertices. Restore protected regions from native doubles.
                    keep=~np.isin(m2,protected);original=np.isin(mm,protected)
                    t2=np.concatenate([t2[keep],tt[original]+len(p2)]);m2=np.r_[m2[keep],mm[original]];p2=np.concatenate([p2,pp])
                    check=deviation(pp,tt,p2,t2,count=8192)
                    if check['max']>1.001:
                        lod['rejected_end_to_end_check']=check;p2,t2,m2=p1,t1,m1;lod['whole_unit_fallback']=True;check=deviation(pp,tt,p2,t2,count=8192)
                    # Every protected triangle retains its ordered positions.
                    for key in protected:
                        old=pp[tt[mm==key]].reshape(-1,9);new=p2[t2[m2==key]].reshape(-1,9)
                        if sorted(map(tuple,old))!=sorted(map(tuple,new)):raise ValueError('protected material changed')
                    accepted=sum(r['operation']=='planar-boundary-skin' for r in skin['patches'])
                    proofs.append({'unit':int(unit),'before':len(tt),'planar':len(t1),'lod_triangles':len(t2),'planar_patches':accepted,'sampled_deviation_mm':check,'lod':lod})
                else:p1,t1,m1=pp,tt,mm;p2,t2,m2=pp,tt,mm
                chunks['planar'].append((p1,t1,m1,int(unit)));chunks['lod'].append((p2,t2,m2,int(unit)))
            totals={}
            for stage,parts in chunks.items():
                offset=0;ps=[];ts=[];ms=[];us=[]
                for pp,tt,mm,unit in parts:ps.append(pp);ts.append(tt+offset);ms.append(mm);us.extend([unit]*len(tt));offset+=len(pp)
                save_mesh(folder,stage,np.concatenate(ps),np.concatenate(ts),np.concatenate(ms),palette,np.array(us));totals[stage]=sum(len(v[1]) for v in parts)
            r={**native,'planar_triangles':totals['planar'],'lod_triangles':totals['lod'],'protected_material_ids':protected,'unit_checks':proofs,'outputs_sha256':{stage+'.glb':digest(folder/(stage+'.glb')) for stage in chunks}}
            (folder/'passes.json').write_text(json.dumps(r,indent=2)+'\n');rows.append(r);print(cid,len(t),'->',totals['planar'],'->',totals['lod'],flush=True)
            del doc,reader,shape,shells;gc.collect()
    report={'hierarchy_sha256':digest(hp),'components':rows,'elapsed_seconds':time.perf_counter()-start,'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_planar_shell.py',ROOT/'python/cad_local_lod.py',ROOT/'python/mesh_parts.py']},'scope':'Definition and placed counts differ. Native .4 mm/.25 rad baseline. Per-native-shell planar skins followed by .25 mm nominal/1 mm sampled visual LOD. Chromatic and unresolved materials preserved exactly. No source removal, hole fill, semantic inference, detector/collision change or runtime installation.'}
    (a.out/('passes.json' if a.optimize else 'inventory.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('TOTAL',sum(r['native_triangles']*r['uses'] for r in rows),flush=True)

if __name__=='__main__':main()
