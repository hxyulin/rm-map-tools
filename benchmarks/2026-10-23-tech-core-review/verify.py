# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent reopen, untouched geometry, and rendered silhouette checks."""
from collections import Counter
import json
from pathlib import Path
from audit import detail, OUT, ROOT
from trial import digest
import numpy as np
from PIL import Image
from gltf_scene import accessor, read_glb, scene_nodes
from simplify_package import scene_triangles


def triangles(doc,blob,node,protected_only=False):
    if 'mesh'not in doc['nodes'][node]:return Counter()
    mesh=doc['meshes'][doc['nodes'][node]['mesh']];result=[]
    for pr in mesh['primitives']:
        if protected_only and not detail.optical(doc,pr):continue
        p=accessor(doc,blob,pr['attributes']['POSITION']);t=accessor(doc,blob,pr['indices']).reshape(-1,3)
        # Round only for comparison of float32-written geometry after transforms.
        if protected_only:
            arrays=[(name,accessor(doc,blob,ai)[t])for name,ai in sorted(pr['attributes'].items())]
            for i in range(len(t)):result.append((pr['material'],tuple((name,a[i].tobytes())for name,a in arrays)))
        else:
            for g in p[t]: result.append((pr['material'],np.round(g.astype(float),7).tobytes()))
    return Counter(result)


def main():
    ledger=json.loads((OUT/'ledger.json').read_text());checks=[]
    for row in ledger['trials']:
        source,target=Path(row['source']),Path(row['output'])
        assert digest(source)==row['source_sha256'] and digest(target)==row['output_sha256']
        sd,sb=read_glb(source);doc,blob=read_glb(target)
        assert sd['materials']==doc['materials'] and len(sd['nodes'])==len(doc['nodes'])
        changed={r['node']for r in row['selections']};untouched=0;protected=0
        for i,world,parent in scene_nodes(sd):
            before,after=sd['nodes'][i],doc['nodes'][i]
            assert {k:v for k,v in before.items()if k!='mesh'}=={k:v for k,v in after.items()if k!='mesh'}
            if 'mesh'not in before:continue
            if i not in changed:
                assert triangles(sd,sb,i)==triangles(doc,blob,i);untouched+=1
            a,b=triangles(sd,sb,i,True),triangles(doc,blob,i,True)
            assert a==b;protected+=sum(a.values())
        for i,world,parent in scene_nodes(doc):
            if 'mesh'not in doc['nodes'][i]:continue
            for p in doc['meshes'][doc['nodes'][i]['mesh']]['primitives']:
                n=len(accessor(doc,blob,p['attributes']['POSITION']));ix=accessor(doc,blob,p['indices'])
                assert len(ix)%3==0 and len(ix) and ix.min()>=0 and ix.max()<n
                for ai in p['attributes'].values():
                    a=accessor(doc,blob,ai);assert len(a)==n and np.isfinite(a).all()
        assert scene_triangles(doc)==row['after_per_core']
        checks.append({'role':row['role'],'policy':row['policy'],'per_core_triangles':scene_triangles(doc),
                       'unchanged_mesh_nodes':untouched,'exact_protected_triangle_rows':protected,
                       'materials_hierarchy_frames_equal':True,'finite_valid_accessors':True})
    report=json.loads((OUT/'review.json').read_text());index={(r['stage'],r['group'],r['view']):r for r in report['views']};metrics=[]
    assert len(index)==6*4*7
    for l in report['levels']:
        for group in ('whole','arm','tool','pedestal'):
            for view in ('oblique','reverse','front','back','side','top','bottom'):
                r=index[(l['id'],group,view)];base=index[(l['role']+'-baseline',group,view)]
                a=np.array(Image.open(r['image']).convert('RGB'));b=np.array(Image.open(base['image']).convert('RGB'))
                assert a.shape==b.shape==(1200,1200,3)
                bg=np.array([192,208,224]);ma=np.any(a!=bg,axis=2);mb=np.any(b!=bg,axis=2)
                colors={}
                for name,channel in [('red',0),('green',1)]:
                    def mask(im):
                        return (im[:,:,channel]>150)&(im[:,:,(channel+1)%3]<120)&(im[:,:,(channel+2)%3]<120)
                    colors[name+'_difference_pixels']=int(np.count_nonzero(mask(a)^mask(b)))
                metrics.append({'stage':l['id'],'group':group,'view':view,
                                'silhouette_difference_fraction':float(np.count_nonzero(ma^mb)/max(1,np.count_nonzero(ma|mb))),**colors})
    sources=[]
    for rel in ('manifest.json','equipment/manifest.json'):
        manifest=ROOT.parent/'rm-simulator/field-2027'/rel
        for asset in json.loads(manifest.read_text())['assets'].values():
            for role in ('visual','collision'):
                p=manifest.parent/asset[role];assert digest(p)==asset[role+'_sha256'];sources.append(str(p))
    (OUT/'verification.json').write_text(json.dumps({'assets':checks,'matched_views':len(index),
        'runtime_sources_unchanged':len(sources),'views':metrics,
        'scope':'Finite rest-pose image masks and exact unchanged/protected geometry; no articulation, continuous shape or simulator collision certification.'},indent=2)+'\n')
    print('Verified',len(checks),'candidates,',len(index),'views and',len(sources),'unchanged runtime sources.')


if __name__=='__main__':main()
