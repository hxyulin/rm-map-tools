# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compact numeric patch instances with source bindings and verified round trips.

This is a source-backed optional IR layer, not a complete CAD serialization.
The NPZ uses uncompressed numeric tables; release compression belongs in tar.zst.
"""
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
from cad_patch_instances import AffinePatchUse,PatchInstanceLayer


KINDS=('quad','triangle')
SCHEMA='rm-affine-patch-layer-v1'
DTYPES={**{k:'<u4' for k in ('faces','components','appearance_targets','colours','boundary_offsets',
                             'source_vertices','source_edges','source_uses','fallback_faces')},
        **{k:'u1' for k in ('templates','markings','orientations','retained_corners')},
        'frames_mm':'<f8','origins_mm':'<f8','edge_vectors_mm':'<f8','edge_vector_indices':'<u4','proof_mm':'<f8'}


def _sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write_layer(layer,output,*,frame_encoding='direct'):
    """Atomically write a new typed-table layer after exact full-use read-back."""
    if frame_encoding not in ('direct','auto'):raise ValueError('unknown requested frame encoding')
    requested_encoding=frame_encoding
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    uses=layer.uses;n=len(uses)
    components=sorted({u.component_id for u in uses});colours=[None]+sorted({u.source_colour for u in uses if u.source_colour is not None})
    component_index={v:i for i,v in enumerate(components)};colour_index={v:i for i,v in enumerate(colours)}
    offsets=[0];vertices=[];edges=[];oriented=[];orientations=[];keep=np.full((n,4),255,dtype='u1')
    for i,u in enumerate(uses):
        vertices.extend(u.source_vertex_ids);edges.extend(u.source_edge_ids);oriented.extend(u.source_oriented_edge_ids)
        orientations.extend(u.orientations);offsets.append(len(vertices))
        keep[i,:len(u.retained_corner_indices)]=u.retained_corner_indices
    values={'faces':[u.source_face_id for u in uses], 'components':[component_index[u.component_id] for u in uses],
            'appearance_targets':[u.appearance_target_id or 0 for u in uses],
            'colours':[colour_index[u.source_colour] for u in uses],
            'templates':[KINDS.index(u.template) for u in uses], 'markings':[u.collision_role=='marking' for u in uses],
            'frames_mm':np.array([u.frame_mm for u in uses]).reshape(n,3,3),
            'proof_mm':np.array([[u.boundary_error_bound_mm,u.source_incidence_error_mm,u.simplification_error_mm,
                                 u.corner_reconstruction_error_mm,u.numeric_guard_mm] for u in uses]).reshape(n,5),
            'boundary_offsets':offsets,'source_vertices':vertices,'source_edges':edges,'source_uses':oriented,
            'orientations':orientations,'retained_corners':keep,'fallback_faces':layer.fallback_face_ids}
    arrays={k:np.asarray(v,dtype=DTYPES[k]) for k,v in values.items()}
    frame_encoding='direct'
    vectors=np.ascontiguousarray(arrays['frames_mm'][:,1:,:].reshape(-1,3))
    records=vectors.view(np.dtype((np.void,24))).reshape(-1)
    _,first,inverse=np.unique(records,return_index=True,return_inverse=True)
    pooled_bytes=n*3*8+len(first)*3*8+n*2*4
    if requested_encoding=='auto' and pooled_bytes<arrays['frames_mm'].nbytes:
        frame_encoding='exact-edge-vector-pool'
        frames=arrays.pop('frames_mm')
        arrays['origins_mm']=np.ascontiguousarray(frames[:,0,:])
        arrays['edge_vectors_mm']=vectors[first]
        arrays['edge_vector_indices']=inverse.astype('<u4').reshape(n,2)
    metadata={'schema':SCHEMA,'source_sha256':layer.source_sha256,'units':'mm','budget_mm':layer.budget_mm,
              'source_face_count':layer.source_face_count,'frame_encoding':frame_encoding,'components':components,'colours':colours,
              'rejection_counts':layer.rejection_counts,
              'scope':'Source-backed finite boundary layer; unsupported faces and complete source topology/styles remain in the checksum-pinned source archive.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage=Path(temporary)/'layer';stage.mkdir()
        np.savez(stage/'instances.npz',**arrays)
        metadata['instances_sha256']=_sha(stage/'instances.npz')
        (stage/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
        loaded=read_layer(stage,expected_source_sha256=layer.source_sha256)
        if loaded!=layer:raise ValueError('patch table roundtrip changed a source use')
        stage.rename(output)
    return {'raw_array_bytes':sum(a.nbytes for a in arrays.values()),'frame_encoding':frame_encoding,
            'exact_edge_vector_definitions':len(first) if frame_encoding!='direct' else None,
            'npz_file_bytes':(output/'instances.npz').stat().st_size,
            'manifest_bytes':(output/'manifest.json').stat().st_size,
            'uses_roundtripped':n,'all_use_fields_preserved':True}


def read_layer(directory,*,expected_source_sha256):
    """Validate tables and reconstruct all finite uses without the CAD kernel.

    Original CAD must still be available to resolve fallback geometry or verify
    native support semantics. This verifies serialization, not CAD equivalence.
    """
    directory=Path(directory);metadata=json.loads((directory/'manifest.json').read_text())
    if metadata.get('schema')!=SCHEMA or metadata.get('units')!='mm':raise ValueError('unknown patch table schema/units')
    if metadata.get('source_sha256')!=expected_source_sha256:raise ValueError('patch layer/source mismatch')
    if _sha(directory/'instances.npz')!=metadata['instances_sha256']:raise ValueError('patch table checksum mismatch')
    budget=metadata['budget_mm']
    if not isinstance(budget,(float,int)) or not np.isfinite(budget) or budget<=0:raise ValueError('invalid stored budget')
    encoding=metadata.get('frame_encoding','direct')
    base=set(DTYPES)-{'frames_mm','origins_mm','edge_vectors_mm','edge_vector_indices'}
    if encoding=='direct':expected=base|{'frames_mm'}
    elif encoding=='exact-edge-vector-pool':expected=base|{'origins_mm','edge_vectors_mm','edge_vector_indices'}
    else:raise ValueError('unknown frame encoding')
    with np.load(directory/'instances.npz',allow_pickle=False) as archive:
        if set(archive.files)!=expected:raise ValueError('missing/unknown patch tables')
        tables={k:archive[k] for k in expected}
    for key,values in tables.items():
        if values.dtype!=np.dtype(DTYPES[key]):raise ValueError('invalid table dtype')
    n=len(tables['faces']);offsets=tables['boundary_offsets']
    if encoding!='direct':
        vectors=tables['edge_vectors_mm'];indices=tables['edge_vector_indices']
        if (vectors.ndim!=2 or vectors.shape[1]!=3 or indices.shape!=(n,2) or
                tables['origins_mm'].shape!=(n,3) or np.any(indices>=len(vectors))):
            raise ValueError('invalid edge vector pool')
        tables['frames_mm']=np.concatenate((tables['origins_mm'][:,None,:],vectors[indices]),axis=1)
    if offsets.shape!=(n+1,) or offsets[0]!=0 or np.any(offsets[1:]<offsets[:-1]):raise ValueError('invalid boundary offsets')
    m=int(offsets[-1])
    shapes={**{k:(n,) for k in ('faces','components','appearance_targets','colours','templates','markings')},
            'frames_mm':(n,3,3),'proof_mm':(n,5),'retained_corners':(n,4),
            **{k:(m,) for k in ('source_vertices','source_edges','source_uses')},
            'orientations':(2*n+2*m,)}
    if any(tables[k].shape!=shape for k,shape in shapes.items()):raise ValueError('invalid patch table dimensions')
    components=metadata['components'];colours=metadata['colours']
    if len(set(components))!=len(components) or any(not isinstance(v,str) or not v for v in components):raise ValueError('invalid component dictionary')
    if not colours or colours[0] is not None or len(set(colours))!=len(colours):raise ValueError('invalid appearance dictionary')
    if any(not isinstance(v,str) for v in colours[1:]):raise ValueError('invalid appearance label')
    if (np.any(tables['components']>=len(components)) or np.any(tables['colours']>=len(colours)) or
            np.any(tables['templates']>1) or np.any(tables['markings']>1) or np.any(tables['orientations']>1)):
        raise ValueError('invalid table dictionary index')
    if not np.isfinite(tables['frames_mm']).all() or not np.isfinite(tables['proof_mm']).all() or np.any(tables['proof_mm']<0):
        raise ValueError('invalid numeric patch payload')
    if np.any(tables['proof_mm'][:,0]>budget):raise ValueError('stored patch exceeds budget')
    faces=list(map(int,tables['faces']));fallback=list(map(int,tables['fallback_faces']))
    if tables['fallback_faces'].ndim!=1 or len(set(faces+fallback))!=len(faces)+len(fallback) or any(v<=0 for v in faces+fallback):
        raise ValueError('duplicate/invalid source face accounting')
    if len(faces)+len(fallback)!=metadata['source_face_count']:raise ValueError('source face coverage changed')
    uses=[]
    for i,face in enumerate(faces):
        a,b=map(int,offsets[i:i+2]);kind=KINDS[int(tables['templates'][i])];count=4 if kind=='quad' else 3
        keep=tuple(map(int,tables['retained_corners'][i,:count]))
        if b-a<3 or len(set(keep))!=count or any(v>=b-a for v in keep):raise ValueError('invalid retained source corners')
        ids=[tuple(map(int,tables[k][a:b])) for k in ('source_vertices','source_edges','source_uses')]
        if any(v<=0 for group in ids for v in group):raise ValueError('invalid source boundary identity')
        orientation=tuple(map(bool,tables['orientations'][2*i+2*a:2*(i+1)+2*b]))
        frame=tuple(tuple(map(float,row)) for row in tables['frames_mm'][i]);proof=tuple(map(float,tables['proof_mm'][i]))
        if np.linalg.norm(np.cross(frame[1],frame[2]))<=1e-20:raise ValueError('singular stored patch')
        uses.append(AffinePatchUse(face,components[int(tables['components'][i])],kind,frame,*ids,orientation,keep,
                                  *proof,colours[int(tables['colours'][i])],int(tables['appearance_targets'][i]) or None,
                                  'marking' if tables['markings'][i] else 'structural'))
    return PatchInstanceLayer(expected_source_sha256,budget,tuple(uses),tuple(fallback),
                              tuple((str(k),int(v)) for k,v in metadata['rejection_counts']),metadata['source_face_count'])
