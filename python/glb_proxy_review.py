# SPDX-License-Identifier: MIT OR Apache-2.0
"""Small GLB proxy writer and exact unselected-payload checks for CAD reviews."""
import copy
import numpy as np
from gltf_scene import read_glb,accessor
from simplify_package import append_accessor

def primitive(doc,binary,triangles,template):
    flat=(triangles*.001).reshape(-1,3).astype(np.float32)
    g=flat.reshape(-1,3,3).astype(float)
    n=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);length=np.linalg.norm(n,axis=1)
    if not np.isfinite(g).all()or (length<=0).any():raise ValueError('proxy has nonfinite or degenerate triangles')
    n/=length[:,None];pr=copy.deepcopy(template)
    pr['attributes']={'POSITION':append_accessor(doc,binary,flat,'VEC3',5126),
        'NORMAL':append_accessor(doc,binary,np.repeat(n,3,axis=0).astype(np.float32),'VEC3',5126)}
    pr['indices']=append_accessor(doc,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125)
    return pr

def unchanged(source,target,changed):
    """Assert unchanged scene metadata, owner mounts and unselected accessors."""
    d,b=read_glb(source);a,ab=read_glb(target);count=0
    assert len(d['nodes'])==len(a['nodes'])and d['materials']==a['materials']and d['scenes']==a['scenes']and d['asset']==a['asset']
    for i,(n,nn)in enumerate(zip(d['nodes'],a['nodes'])):
        assert {k:v for k,v in n.items()if k!='mesh'}=={k:v for k,v in nn.items()if k!='mesh'}
        if 'mesh'not in n or i in changed:continue
        pp=d['meshes'][n['mesh']]['primitives'];qq=a['meshes'][nn['mesh']]['primitives'];assert len(pp)==len(qq)
        for x,y in zip(pp,qq):
            assert {k:v for k,v in x.items()if k not in ['attributes','indices']}=={k:v for k,v in y.items()if k not in ['attributes','indices']}
            assert x['attributes'].keys()==y['attributes'].keys()
            for key in x['attributes']:
                p=accessor(d,b,x['attributes'][key]);q=accessor(a,ab,y['attributes'][key]);assert p.dtype==q.dtype and p.shape==q.shape and p.tobytes()==q.tobytes()
            assert np.array_equal(accessor(d,b,x['indices']),accessor(a,ab,y['indices']))
        count+=1
    return count
