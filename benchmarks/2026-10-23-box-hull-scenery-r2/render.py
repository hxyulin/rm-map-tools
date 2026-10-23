"""Matched local/context renders of owner-local scenery hull proposals."""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import ConvexHull

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('adaptive_scenery',Path(__file__).with_name('adaptive.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
OUT=a.OUT;base=a.base;original=base.original
spec=importlib.util.spec_from_file_location('old_primitive_render',ROOT/'benchmarks/2026-10-23-box-primitive-candidates/render.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
import collision_review_render as r


def colored(g,ids=None,color=(.9,.45,.16)):
    data=list(old.data(g,[.64,.67,.7]))
    if ids is not None:data[1][ids]=color
    return tuple(data)


def main():
    rows=json.loads((OUT/'adaptive.json').read_text());screen=json.loads((OUT/'screen.json').read_text())
    source=screen['source'];doc,comp,nodes=original.load_nodes(source)
    subjects=[];renders=[]
    for ni in [354,587,710,660]:
        select=[x for x in rows if x['node']==ni and x['proof']['inward_envelope_limit_mm']==.5]
        if ni in [354,587]:select=[x for x in select if x['source_triangles'] in [482,484]]
        else:select=select[:1]
        if not select:continue
        ids=np.concatenate([x['source_triangle_indices'] for x in select]);assert len(ids)==len(set(ids))
        g=nodes[ni];chosen=g[ids];candidates=[]
        for row in select:
            p=np.asarray(row['hull_vertices_mm']);candidates.append(p[ConvexHull(p).simplices])
        cg=np.concatenate(candidates);keep=np.ones(len(g),bool);keep[ids]=False
        after=np.concatenate([g[keep],cg]);after_ids=np.arange(keep.sum(),len(after))
        key=f'scenery-{ni}'
        target=OUT/f'{key}-selected-hulls-diagnostic.glb';old.preview_glb(target,cg,source,ni)
        subjects.append(dict(key=key,node=ni,component=comp[ni],selected_islands=[x['island'] for x in select],
            source_selected_triangles=len(chosen),candidate_triangles=len(cg),mesh_savings=len(chosen)-len(cg),
            native_hull_leaves=len(select),native_mesh_triangles_replaced=len(chosen),
            envelope_inward_bound_mm=max(x['proof']['maximum_original_hull_vertex_distance_mm']for x in select),
            strict_sampled_max_mm=max(x['strict_sampled_max_mm']for x in select),
            diagnostic_glb=str(target),diagnostic_sha256=original.digest(target),source_triangle_indices=ids.tolist(),
            status='conditional-strand-gap-fill-low-priority' if ni in [354,587] else 'rejected-concavity-fill',
            interpretation='Three-strand bundles become solid hulls; gaps fill. These are not solid rectangular structural members.' if ni in [354,587] else 'Whole-member hull removes a major concavity.',
            contact_approved=False))
        with tempfile.TemporaryDirectory() as td:
            tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
            if not helper.is_file():
                helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
            for scope in ['local','context']:
                before=colored(chosen,np.arange(len(chosen))) if scope=='local' else colored(g,ids)
                result=colored(cg,np.arange(len(cg)),(.18,.65,.85)) if scope=='local' else colored(after,after_ids,(.18,.65,.85))
                # Common framing uses the selected parts, including in context.
                focus=old.data(chosen,[.6,.6,.6])[0]
                for direction,label in [((1,.65,1),'oblique'),((-1,.65,-1),'reverse')]:
                    for stage,data in [('source',before),('proxy',result)]:
                        path=OUT/f'{key}-{scope}-{label}-{stage}.webp'
                        Image.fromarray(r.raster(data,focus,direction,helper,tmp)).save(path,lossless=True)
                        renders.append(dict(key=key,node=ni,scope=scope,view=label,stage=stage,path=str(path),sha256=original.digest(path)))
    assert original.digest(Path(source))==screen['source_sha256']
    (OUT/'renders.json').write_text(json.dumps(dict(subjects=subjects,views=renders),indent=2)+'\n')
    print(json.dumps(subjects,indent=2))


if __name__=='__main__':main()
