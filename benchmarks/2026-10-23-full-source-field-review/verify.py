"""Reopen complete reference and verify every source payload and occurrence."""
import sys,json,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,scene_nodes,local_matrix,accessor
from plan_cad_lods import build_plan,digest
OUT=ROOT/'out/rmuc2027-full-source-field-review'
def main():
 source=json.loads((OUT/'source.json').read_text());d,b=read_glb(source['reference']);offset=0;mi=ai=vi=0;materials=0
 for row in source['components']:
  sd,sb=read_glb(row['path']);assert digest(Path(row['path']))==row['sha256'];assert b[offset:offset+len(sb)]==sb
  assert d['materials'][materials:materials+len(sd['materials'])]==sd['materials']
  for j,mesh in enumerate(sd['meshes']):
   actual=d['meshes'][mi+j];assert len(actual['primitives'])==len(mesh['primitives'])
   for x,y in zip(actual['primitives'],mesh['primitives']):
    assert x['material']==y['material']+materials;assert np.array_equal(accessor(d,b,x['indices']),accessor(sd,sb,y['indices']))
    for key in y['attributes']:assert np.array_equal(accessor(d,b,x['attributes'][key]),accessor(sd,sb,y['attributes'][key]))
  offset+=len(sb);offset+=-offset%4;mi+=len(sd['meshes']);ai+=len(sd['accessors']);vi+=len(sd['bufferViews']);materials+=len(sd['materials'])
 h=json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_text());plan=build_plan(h);occ=[n for n in plan['nodes'] if n['component_id']];roots=d['scenes'][0]['nodes'];assert len(roots)==len(occ)==171
 for index,n in zip(roots,occ):
  actual=d['nodes'][index];expected=np.array(n['world_matrix_mm']);expected[:3,3]/=1000;assert np.array_equal(local_matrix(actual),expected);assert actual['extras']['component_id']==n['component_id']
 count=sum(d['accessors'][p['indices']]['count']//3 for i,_,_ in scene_nodes(d) if 'mesh' in d['nodes'][i] for p in d['meshes'][d['nodes'][i]['mesh']]['primitives']);assert count==source['placed_triangles']==8311552
 report={'reference_sha256':digest(Path(source['reference'])),'all_source_binary_payloads_byte_exact':True,'all_material_records_exact':True,'all_primitive_positions_normals_indices_exact':True,'all_171_hierarchy_world_placements_exact':True,'placed_triangles':count,'component_definitions':len(source['components']),'original_step_faces_exactly_partitioned':source['original_source_face_ids_exactly_partitioned'],'mapping_limit':source['mapping_limit'],'producer_sha256':digest(Path(__file__))};(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
