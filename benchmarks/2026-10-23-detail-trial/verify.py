"""Independently reopen ledger exports and check exact selection/protections."""
import json
from pathlib import Path
import numpy as np
from run import OUT, accessor, counts, digest, optical, read_glb, scene_nodes


def main():
    report=json.loads((OUT/'ledger.json').read_text())
    for path,meta in report['inputs'].items():
        assert digest(Path(path))==meta['sha256']
    for result in report['assets']:
        source=Path(result['input']);target=Path(result['output'])
        assert digest(source)==result['input_sha256']
        assert digest(target)==result['output_sha256']
        sd,sb=read_glb(source);cd,cb=read_glb(target)
        metadata=report['inputs'][str(source)]
        assert counts(sd,metadata['placements'])==result['before']
        assert counts(cd,metadata['placements'])==result['after']
        assert sd['materials']==cd['materials']
        assert len(sd['nodes'])==len(cd['nodes'])
        selections={n['node']:n['retained_triangle_indices_by_baseline_primitive'] for n in result['nodes']}
        for i,w,parent in scene_nodes(sd):
            sn=sd['nodes'][i];cn=cd['nodes'][i]
            assert {k:v for k,v in sn.items() if k!='mesh'}=={k:v for k,v in cn.items() if k!='mesh'}
            if 'mesh' not in sn:continue
            spr=sd['meshes'][sn['mesh']]['primitives'];cpr=cd['meshes'][cn['mesh']]['primitives'];j=0
            for pi,sp in enumerate(spr):
                t=(accessor(sd,sb,sp['indices']) if 'indices' in sp else np.arange(sd['accessors'][sp['attributes']['POSITION']]['count'])).reshape(-1,3)
                ids=np.asarray(selections[i][pi]) if i in selections else np.arange(len(t))
                if optical(sd,sp):assert np.array_equal(ids,np.arange(len(t)))
                if not len(ids):continue
                cp=cpr[j];j+=1
                assert np.array_equal(t[ids].ravel(),accessor(cd,cb,cp['indices']))
                assert sp.get('material')==cp.get('material')
                for attr,idx in sp['attributes'].items():
                    assert np.array_equal(accessor(sd,sb,idx),accessor(cd,cb,cp['attributes'][attr]))
            assert j==len(cpr)
        for node in result['nodes']:
            for piece in node['parts']:
                if piece['removed']:
                    assert max(piece['span_mm'])<result['extent_mm_strict']
                    assert piece['maximum_vertex_backing_distance_mm']<result['vertex_backing_mm_strict']
                    assert piece['reason']=='explicit-lossy-size-and-backing-omission'
    print(f"Verified {len(report['inputs'])} immutable inputs, {len(report['assets'])} reopened candidates, exact retained arrays, optical protection, strict bounds, node hierarchy/transforms.")


if __name__=='__main__':main()
