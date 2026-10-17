# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Boundary-defined planar skins for explicitly selected source members.

This changes tessellation, not semantic ownership. Holes and material regions
remain separate. Near-planar admission is an explicit numerical allowance.
"""
from collections import defaultdict
import math
import numpy as np


def planar_skin(points_mm,triangles,material_ids,*,plane_tolerance_mm=.001,
                boundary_tolerance_mm=.001,minimum_triangles=8,
                protected_material_ids=()):
    """Replace connected nearly coplanar patches by retained boundary loops.

    Every boundary must be a disjoint closed loop; nonmanifold patches retain
    input. Collinear subdivisions can be removed within the boundary allowance.
    Original kept boundary positions are retained. Output records the loops for
    future tessellation, source triangle membership and sampled deviation.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    import vtk
    from mesh_quality import deviation
    p=np.asarray(points_mm,float);t=np.asarray(triangles);m=np.asarray(material_ids)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or m.shape!=(len(t),) or not np.issubdtype(m.dtype,np.integer):raise ValueError('invalid planar skin input')
    if not all(math.isfinite(x) and x>0 for x in [plane_tolerance_mm,boundary_tolerance_mm]) or type(minimum_triangles) is not int or minimum_triangles<2:raise ValueError('invalid planar skin policy')
    # Exact shared positions only: do not weld nearby independent sheets.
    p,inv=np.unique(p[t].reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3)
    xyz=p[t];normals=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);areas=np.linalg.norm(normals,axis=1);normals/=np.maximum(areas[:,None],1e-30);edges=defaultdict(list)
    for i,tri in enumerate(t):
        for a,b in zip(tri,np.roll(tri,-1)):edges[tuple(sorted((int(a),int(b))))].append(i)
    rows=[];cols=[]
    for edge,uses in edges.items():
        if len(uses)!=2:continue
        a,b=uses
        if m[a]!=m[b] or m[a] in protected_material_ids or min(areas[a],areas[b])<1e-12:continue
        if abs(normals[a]@normals[b])<.999999:continue
        if max(abs((xyz[b]-xyz[a,0])@normals[a]))>plane_tolerance_mm:continue
        rows.extend([a,b]);cols.extend([b,a])
    _,labels=connected_components(coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(t),len(t))).tocsr(),directed=False)
    result=[];materials=[];records=[]
    for label in np.unique(labels):
        ids=np.flatnonzero(labels==label);old=t[ids];key=m[ids[0]]
        if len(ids)<minimum_triangles or key in protected_material_ids:result.extend(old);materials.extend([key]*len(old));continue
        record={'input_triangle_indices':ids.tolist(),'material_id':int(key),'before_triangles':len(old),'operation':'retain-input'}
        try:
            vertices=np.unique(old);origin=p[vertices].mean(0);_,_,basis=np.linalg.svd(p[vertices]-origin,full_matrices=False);normal=basis[2]
            if normals[ids].sum(0)@normal<0:normal=-normal
            axis=basis[0];up=np.cross(normal,axis);frame=np.array([axis,up,normal]);local=(p-origin)@frame.T;residual=float(abs(local[vertices,2]).max())
            if residual>plane_tolerance_mm:raise ValueError('patch accumulates nonplanarity')
            ee=np.sort(np.concatenate([old[:,[0,1]],old[:,[1,2]],old[:,[2,0]]]),axis=1);ee,count=np.unique(ee,axis=0,return_counts=True)
            if np.any(count>2):raise ValueError('nonmanifold patch')
            boundary=ee[count==1];adj=defaultdict(list)
            for a,b in boundary:adj[int(a)].append(int(b));adj[int(b)].append(int(a))
            if not adj or any(len(neighbors)!=2 for neighbors in adj.values()):raise ValueError('boundary is not disjoint closed loops')
            unused=set(adj);loops=[]
            while unused:
                first=min(unused);loop=[first];previous=first;current=adj[first][0]
                while current!=first:
                    if current not in unused:raise ValueError('boundary repeats a vertex')
                    loop.append(current);unused.remove(current);next_vertex=next(v for v in adj[current] if v!=previous);previous,current=current,next_vertex
                unused.remove(first)
                # Test removal against every original sample along the resulting
                # chord, so repeated tiny steps cannot accumulate drift.
                retained=list(range(len(loop)))
                while len(retained)>3:
                    removed=False
                    for j,k in enumerate(retained):
                        aa=retained[j-1];bb=retained[(j+1)%len(retained)];start=p[loop[aa]];end=p[loop[bb]];chord=end-start;length=chord@chord
                        if length<1e-20:continue
                        span=list(range(aa,bb+1)) if aa<bb else list(range(aa,len(loop)))+list(range(bb+1));samples=p[np.array(loop)[span]];u=(samples-start)@chord/length
                        if u.min()>=0 and u.max()<=1 and np.linalg.norm(samples-(start+u[:,None]*chord),axis=1).max()<=boundary_tolerance_mm:
                            retained.pop(j);removed=True;break
                    if not removed:break
                loops.append([loop[k] for k in retained])
            used=np.unique(np.concatenate(loops));mapping={int(k):i for i,k in enumerate(used)};vpoints=vtk.vtkPoints();vpoints.SetDataTypeToDouble()
            for v in used:vpoints.InsertNextPoint(float(local[v,0]),float(local[v,1]),0)
            cells=vtk.vtkCellArray()
            for loop in loops:
                cells.InsertNextCell(len(loop)+1)
                for v in loop+[loop[0]]:cells.InsertCellPoint(mapping[v])
            data=vtk.vtkPolyData();data.SetPoints(vpoints);data.SetLines(cells);triangulator=vtk.vtkContourTriangulator();triangulator.SetInputData(data);triangulator.Update();output=triangulator.GetOutput();new=[]
            for k in range(output.GetNumberOfCells()):
                cell=output.GetCell(k)
                if cell.GetNumberOfPoints()!=3:raise ValueError('nontriangular skin')
                new.append([used[cell.GetPointId(j)] for j in range(3)])
            new=np.asarray(new,dtype=np.int64).reshape(-1,3)
            if not len(new) or len(new)>=len(old):raise ValueError('no triangle saving')
            q=p[new];cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);new[(cross@normal)<0]=new[(cross@normal)<0][:,[0,2,1]]
            new_area=np.linalg.norm(cross,axis=1).sum()
            if abs(new_area-areas[ids].sum())>max(1e-6,areas[ids].sum()*1e-7):raise ValueError('skin area differs')
            quality=deviation(p,old,p,new,count=min(16384,max(96,len(old))))
            if quality['max']>2*(plane_tolerance_mm+boundary_tolerance_mm):raise ValueError('skin sampled guard failed')
            record.update(operation='planar-boundary-skin',after_triangles=len(new),maximum_planarity_mm=residual,boundary_loops_source_vertices=loops,source_frame={'origin_mm':origin.tolist(),'axes':frame.tolist()},sampled_deviation_mm=quality);result.extend(new);materials.extend([key]*len(new))
        except ValueError as error:record['reason']=str(error);record['after_triangles']=len(old);result.extend(old);materials.extend([key]*len(old))
        records.append(record)
    result=np.asarray(result,dtype=np.int64);used,inv=np.unique(result,return_inverse=True)
    accepted=[r for r in records if r['operation']=='planar-boundary-skin'];skin_vertices=np.unique(np.concatenate([loop for r in accepted for loop in r['boundary_loops_source_vertices']])) if accepted else np.array([],dtype=np.int64);skin_map={int(v):i for i,v in enumerate(skin_vertices)}
    for r in accepted:r['boundary_loops_vertex_indices']=[[skin_map[v] for v in loop] for loop in r['boundary_loops_source_vertices']]
    return p[used],inv.reshape(-1,3),np.asarray(materials,dtype=m.dtype),{'pass':'planar-boundary-skin-v1','plane_tolerance_mm':plane_tolerance_mm,'boundary_tolerance_mm':boundary_tolerance_mm,'before_triangles':len(t),'after_triangles':len(result),'boundary_vertex_positions_mm':p[skin_vertices].tolist(),'boundary_source_vertex_indices':skin_vertices.tolist(),'patches':records,'scope':'Retessellated planar shell patches, preserving holes/materials. Numerical plane/boundary tolerance and sampled check, not a continuous equality certificate.'}
