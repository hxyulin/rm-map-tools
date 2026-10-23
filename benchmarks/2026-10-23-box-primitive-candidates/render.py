"""Render isolated collision screening proposals; never install these previews."""
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import ConvexHull

from scan import ROOT, OUT, load_nodes, box_points, FACES, digest
import collision_review_render as raster
from gltf_scene import write_glb, read_glb
from simplify_package import append_accessor
from mesh_quality import distances


def data(g, color):
    g = g * .001 @ np.array([[1,0,0],[0,0,-1],[0,1,0]])
    return (g,np.tile(color,(len(g),1)),np.zeros((len(g),3,2)),
            np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),
            np.zeros((1,1,3),np.uint8))


def preview_glb(path,g,source,node):
    doc={'asset':{'version':'2.0','extras':{'diagnostic_only':True,
         'collision_approved':False,'source':source,'source_node':node}},
         'scenes':[{'nodes':[0]}],'scene':0,'nodes':[{'mesh':0}],
         'meshes':[{'primitives':[]}],'materials':[{'pbrMetallicRoughness':{
             'baseColorFactor':[.15,.55,.8,1],'metallicFactor':0,'roughnessFactor':1}}],
         'accessors':[],'bufferViews':[],'buffers':[{'byteLength':0}]}
    b=bytearray(); p=(g*.001).reshape(-1,3).astype(np.float32)
    pr={'attributes':{'POSITION':append_accessor(doc,b,p,'VEC3',5126)},
        'indices':append_accessor(doc,b,np.arange(len(p),dtype=np.uint32),'SCALAR',5125),'material':0}
    doc['meshes'][0]['primitives']=[pr];doc['buffers'][0]['byteLength']=len(b)
    write_glb(path,doc,bytes(b)); d,_=read_glb(path)
    assert d['asset']['extras']['diagnostic_only']


def main():
    summary=json.loads((OUT/'results.json').read_text())
    subjects=[('tech-core',68,'box'),('arena-static',260,'hull'),('outpost',10,'hull')]
    views=[]; details=[]
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);helper=tmp/'raster'
        subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for asset,ni,kind in subjects:
            collection=summary['boxes'] if kind=='box' else summary['convex_hulls']
            row=next(x for x in collection if x['asset']==asset and x['node']==ni)
            _,_,nodes=load_nodes(row['source']);g=nodes[ni]
            if kind=='box':
                fit=row['best'];c,f,h=map(np.asarray,[fit['center_mm'],fit['axes_columns'],fit['half_extents_mm']])
                candidate=box_points(c,f,h)[FACES]
                stats={k:fit[k] for k in ['symmetric_sampled_max_mm','source_outside_max_mm','reverse_max_mm','reverse_sample_count','area_p99_surface_mm','area_fraction_surface_over_1mm','half_extents_mm']}
            else:
                p=np.unique(g.reshape(-1,3),axis=0);hull=ConvexHull(p);candidate=p[hull.simplices]
                stats={k:row[k] for k in ['reverse_sampled_max_mm','hull_vertices','hull_facets','reverse_samples']}
            key=f'{asset}-{ni}-{kind}';target=OUT/(key+'-diagnostic.glb')
            preview_glb(target,candidate,row['source'],ni)
            # More sampling on hull previews: the coarse screen is not a bound.
            if kind=='hull':
                from scan import area_samples
                probes=np.concatenate([candidate.reshape(-1,3),area_samples(candidate,50000,seed=987)])
                vals=distances(probes,g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3))
                stats['dense_reverse_sampled_max_mm']=float(vals.max());stats['dense_reverse_samples']=len(probes)
            details.append(dict(key=key,asset=asset,node=ni,kind=kind,component=row['component'],
                source_triangles=len(g),preview_triangles=len(candidate),placements=row['placements'],
                preview=str(target),preview_sha256=digest(target),measurements=stats,
                status='investigation_only'))
            before=data(g,[.65,.65,.65]);after=data(candidate,[.3,.65,.8]);focus=before[0]
            for direction,label in [((1,.65,1),'oblique'),((-1,.65,-1),'reverse')]:
                for stage,item in [('source',before),('proxy',after)]:
                    path=OUT/f'{key}-{label}-{stage}.webp'
                    Image.fromarray(raster.raster(item,focus,direction,helper,tmp)).save(path,lossless=True)
                    views.append(dict(key=key,view=label,stage=stage,path=str(path),sha256=digest(path)))
    for path,sha in summary['pins'].items():assert digest(Path(path))==sha
    (OUT/'renders.json').write_text(json.dumps(dict(subjects=details,views=views),indent=2)+'\n')
    print(json.dumps(details,indent=2))


if __name__=='__main__':main()
