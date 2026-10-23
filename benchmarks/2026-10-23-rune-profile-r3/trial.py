"""Bounded local collision LOD on thin Rune arm plates; visuals untouched."""
import importlib.util,json,sys,tempfile,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates'))
import scan
from cad_local_lod import guarded_vertex_lod
from mesh_quality import distances
import collision_review_render as raster
OUT=ROOT/'out/rmuc2027-rune-profile-r3'


def topology(p,t):
    p,inv=np.unique(p[t].reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3)
    edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1)
    e,count=np.unique(edges,axis=0,return_counts=True)
    n,_=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(p),len(p))),directed=False)
    return dict(vertices=len(p),triangles=len(t),edges=len(e),euler=len(p)-len(e)+len(t),
        components=n,boundary_edges=int(sum(count==1)),nonmanifold_edges=int(sum(count>2)))


def samples(g):
    return np.concatenate([g.reshape(-1,3),g.mean(1),(g[:,0]+g[:,1])/2,(g[:,1]+g[:,2])/2,(g[:,2]+g[:,0])/2,scan.area_samples(g,40000,seed=711)])


def data(g,color):
    return (g*.001@np.array([[1,0,0],[0,0,-1],[0,1,0]]),np.tile(color,(len(g),1)),
        np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),np.zeros((1,1,3),np.uint8))


def run():
    OUT.mkdir(exist_ok=True);ref=json.loads(scan.REF.read_text());info=ref['roles']['collision']['assets']['rune'];source=Path(info['path'])
    assert scan.digest(source)==info['sha256'];doc,components,nodes=scan.load_nodes(source);rows=[]
    for ni,g in nodes.items():
        if '/arm-'not in components[ni] or len(g)<500:continue
        p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3)
        _,_,vt=np.linalg.svd(p-p.mean(0),full_matrices=False);span=np.ptp(p@vt.T,axis=0)
        if min(span)>8 or sorted(span)[1]<50:continue
        before=topology(p,t)
        q,f,_,guard=guarded_vertex_lod(p,t,np.zeros(len(t),np.int32),error_mm=.5,sampled_limit_mm=1,
            sample_count=8192,maximum_iterations=8)
        after=topology(q,f);target=q[f]
        forward=distances(samples(g),q,f);reverse=distances(samples(target),p,t)
        maximum=max(float(forward.max()),float(reverse.max()))
        compatible=all(before[k]==after[k]for k in ['components','euler','boundary_edges'])and after['nonmanifold_edges']<=before['nonmanifold_edges']
        row=dict(asset='rune',node=ni,name=doc['nodes'][ni].get('name'),component=components[ni],source=str(source),source_sha256=info['sha256'],
            before_triangles=len(g),after_triangles=len(f),placed_saving=(len(g)-len(f))*info['placements'],
            span_mm=span.tolist(),forward_max_mm=float(forward.max()),reverse_max_mm=float(reverse.max()),
            source_probe_count=len(forward),target_probe_count=len(reverse),topology_before=before,topology_after=after,
            topology_compatible=compatible,status='candidate'if maximum<=1 and compatible and len(f)<len(g)else'rejected',
            guard=guard,contact_approved=False,visual_unchanged=True)
        rows.append(row);np.savez_compressed(OUT/f'node-{ni}.npz',points_mm=q,triangles=f)
        print(ni,len(g),len(f),maximum,compatible,row['status'],flush=True)
    assert scan.digest(source)==info['sha256']
    (OUT/'results.json').write_text(json.dumps(dict(source=str(source),source_sha256=info['sha256'],rows=rows,
        nominal_error_mm=.5,sampled_limit_mm=1.,scope='Installed Rune thin arm plate collisions only. No native fitting, visuals or installed changes.'),indent=2)+'\n')
    render(nodes,rows)


def render(nodes,rows):
    selected=sorted([r for r in rows if r['status']=='candidate'],key=lambda r:-r['placed_saving'])[:3];views=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        if not helper.is_file():
            helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for row in selected:
            g=nodes[row['node']];z=np.load(OUT/f"node-{row['node']}.npz");target=z['points_mm'][z['triangles']]
            p=np.unique(g.reshape(-1,3),axis=0);_,_,vt=np.linalg.svd(p-p.mean(0),full_matrices=False)
            normal=vt[-1]@np.array([[1,0,0],[0,0,-1],[0,1,0]])
            for name,direction in [('face',normal),('oblique',(1,.65,1))]:
                for stage,geometry,color in [('source',g,(.85,.45,.18)),('candidate',target,(.18,.65,.85))]:
                    path=OUT/f"node-{row['node']}-{name}-{stage}.webp"
                    Image.fromarray(raster.raster(data(geometry,color),data(g,color)[0],direction,helper,tmp)).save(path,lossless=True)
                    views.append(dict(node=row['node'],view=name,stage=stage,path=str(path),sha256=scan.digest(path)))
    (OUT/'renders.json').write_text(json.dumps(views,indent=2)+'\n')


if __name__=='__main__':
    if '--render-only' in sys.argv:
        result=json.loads((OUT/'results.json').read_text());render(scan.load_nodes(result['source'])[2],result['rows'])
    else:run()
