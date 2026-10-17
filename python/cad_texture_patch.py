# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bounded rectangular texture replacement for explicitly qualified planar artwork."""
import math
import numpy as np


def _clip(poly,axis,limit,sign):
    if not len(poly):return np.empty((0,3))
    out=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        da=sign*(a[axis]-limit);db=sign*(b[axis]-limit);ina=da>=0;inb=db>=0
        if ina:out.append(a)
        if ina!=inb:out.append(a+(b-a)*(da/(da-db)))
    return np.asarray(out).reshape(-1,3)


def replace_planar_rectangle(points_mm,triangles,triangle_srgb,*,origin_mm,axes,
                             bounds_uv_mm,height_limit_mm=.1):
    """Subtract a finite UV rectangle from near-planar triangles and add a quad.

    Clip crossing triangles against four exact half-planes, preserving outside
    pieces and all triangles outside the admitted height band. The caller owns
    the source appearance bake, aperture qualification and source-member policy.
    UV V=0 is the image's top row (+V). Output quad positions lie on height zero.
    """
    p=np.asarray(points_mm,float);t=np.asarray(triangles);c=np.asarray(triangle_srgb,float);o=np.asarray(origin_mm,float);frame=np.asarray(axes,float);bounds=np.asarray(bounds_uv_mm,float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not len(t) or not np.issubdtype(t.dtype,np.integer) or t.min()<0 or t.max()>=len(p) or c.shape!=(len(t),3) or not np.isfinite(c).all():raise ValueError('invalid texture patch mesh')
    if o.shape!=(3,) or frame.shape!=(3,3) or bounds.shape!=(4,) or not np.isfinite(np.r_[o,frame.ravel(),bounds]).all() or not np.allclose(frame@frame.T,np.eye(3),atol=1e-10,rtol=0) or not np.isclose(np.linalg.det(frame),1,atol=1e-10,rtol=0) or np.any(bounds[2:]<=bounds[:2]) or not math.isfinite(height_limit_mm) or height_limit_mm<=0:raise ValueError('invalid texture patch frame')
    g=p[t];local=(g-o)@frame.T;parts=[];colors=[];removed=[];partial=[];untouched=[];affected_area=0.
    for i,tri in enumerate(local):
        if abs(tri[:,2]).max()>height_limit_mm or np.any(tri[:,:2].max(0)<=bounds[:2]) or np.any(tri[:,:2].min(0)>=bounds[2:]):parts.append(g[i,None]);colors.append(c[i,None]);untouched.append(i);continue
        inside=tri;outside=[]
        for axis,limit,sign in [(0,bounds[0],1),(0,bounds[2],-1),(1,bounds[1],1),(1,bounds[3],-1)]:
            piece=_clip(inside,axis,limit,-sign)
            if len(piece)>=3:outside.append(piece)
            inside=_clip(inside,axis,limit,sign)
        if len(inside)<3:parts.append(g[i,None]);colors.append(c[i,None]);untouched.append(i);continue
        area=sum(np.linalg.norm(np.cross(inside[j]-inside[0],inside[j+1]-inside[0]))/2 for j in range(1,len(inside)-1))
        if area<1e-10:parts.append(g[i,None]);colors.append(c[i,None]);untouched.append(i);continue
        affected_area+=area
        if not outside:removed.append(i)
        else:partial.append(i)
        for polygon in outside:
            xyz=polygon@frame+o;faces=np.array([[xyz[0],xyz[j],xyz[j+1]] for j in range(1,len(xyz)-1)]);valid=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)>1e-10;faces=faces[valid]
            if len(faces):parts.append(faces);colors.append(np.tile(c[i],(len(faces),1)))
    remaining=np.concatenate(parts) if parts else np.empty((0,3,3));u0,v0,u1,v1=bounds;quad=np.array([[u0,v0,0],[u1,v0,0],[u1,v1,0],[u0,v1,0]])@frame+o
    return {'positions_mm':remaining.reshape(-1,3),'triangles':np.arange(len(remaining)*3).reshape(-1,3),'triangle_srgb':np.concatenate(colors) if colors else np.empty((0,3)),'quad_positions_mm':quad,'quad_triangles':np.array([[0,1,2],[0,2,3]],dtype=np.uint32),'quad_uv':np.array([[0,1],[1,1],[1,0],[0,0]],dtype=np.float32),'proof':{'pass':'bounded-planar-artwork-quad-v1','origin_mm':o.tolist(),'axes':frame.tolist(),'bounds_uv_mm':bounds.tolist(),'height_limit_mm':height_limit_mm,'before_triangles':len(t),'remaining_triangles':len(remaining),'quad_triangles':2,'removed_input_triangle_indices':removed,'clipped_input_triangle_indices':partial,'untouched_input_triangle_indices':untouched,'replaced_area_sum_mm2':float(affected_area),'rectangle_area_mm2':float((u1-u0)*(v1-v0)),'scope':'Explicit finite planar appearance replacement; source coverage/apertures require separate qualification. No new collision or source-material ownership.'}}


def attach_colour_texture(doc,binary,*,node_index,positions_m,triangles,uv,png_bytes,
                          name='source-appearance-bake',metadata=None):
    """Append a base-colour PNG primitive with glTF UVs and linear factor one.

    The PNG is sRGB base colour. No normal texture, tangent or inferred emissive
    behaviour is introduced. Image rows map to V increasing downward. Clamp
    wrapping and trilinear mip filtering keep UV borders from repeating.
    """
    import copy
    p=np.asarray(positions_m,dtype='<f4');t=np.asarray(triangles,dtype='<u4');tex=np.asarray(uv,dtype='<f4')
    if p.ndim!=2 or p.shape[1]!=3 or t.ndim!=2 or t.shape[1]!=3 or not len(t) or t.max()>=len(p) or tex.shape!=(len(p),2) or not np.isfinite(p).all() or not np.isfinite(tex).all() or np.any((tex<0)|(tex>1)) or not png_bytes.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('invalid textured primitive')
    node=doc['nodes'][node_index]
    if 'mesh' not in node:raise ValueError('texture target has no mesh')
    data=bytearray(binary)
    def view(payload,target=None):
        data.extend(b'\0'*(-len(data)%4));v={'buffer':0,'byteOffset':len(data),'byteLength':len(payload)}
        if target is not None:v['target']=target
        doc['bufferViews'].append(v);data.extend(payload);return len(doc['bufferViews'])-1
    def acc(array,kind,component,target):
        a={'bufferView':view(array.tobytes(),target),'componentType':component,'count':len(array),'type':kind}
        if kind=='VEC3':a.update(min=array.min(0).tolist(),max=array.max(0).tolist())
        doc['accessors'].append(a);return len(doc['accessors'])-1
    normal=np.cross(p[t[0,1]]-p[t[0,0]],p[t[0,2]]-p[t[0,0]]);length=np.linalg.norm(normal)
    if length<=1e-20:raise ValueError('degenerate texture quad')
    normals=np.tile(normal/length,(len(p),1)).astype('<f4');image={'bufferView':view(png_bytes),'mimeType':'image/png','name':name};doc.setdefault('images',[]).append(image);doc.setdefault('samplers',[]).append({'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071});doc.setdefault('textures',[]).append({'source':len(doc['images'])-1,'sampler':len(doc['samplers'])-1});doc['materials'].append({'name':name,'pbrMetallicRoughness':{'baseColorTexture':{'index':len(doc['textures'])-1,'texCoord':0},'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':.8},'doubleSided':True,'extras':{'source_appearance_bake':metadata or {},'colour_space':'sRGB base colour; factor is linear one'}});primitive={'attributes':{'POSITION':acc(p,'VEC3',5126,34962),'NORMAL':acc(normals,'VEC3',5126,34962),'TEXCOORD_0':acc(tex,'VEC2',5126,34962)},'indices':acc(t.reshape(-1),'SCALAR',5125,34963),'material':len(doc['materials'])-1,'mode':4};mesh=copy.deepcopy(doc['meshes'][node['mesh']]);mesh['primitives'].append(primitive);node['mesh']=len(doc['meshes']);doc['meshes'].append(mesh);doc['buffers']=[{'byteLength':len(data)}];return bytes(data)
