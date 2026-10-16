# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""A merged STEP keeps disjoint shell wrappers, analytic faces and shared instances."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

import numpy as np
from cad_document import CadDocument
from cad_components import build_catalog
from cad_hierarchy import remap_record,write_hierarchy,native_validate,verify_assembly_graph,verify_source_placements
from cad_partition import compile_partition
from p21split import Splitter,forward_closure


def shell_fixture(path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.STEPControl import STEPControl_Writer,STEPControl_ShellBasedSurfaceModel
    compound=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(compound)
    for dimensions in [(10,20,30),(40,50,60)]:builder.Add(compound,BRepPrimAPI_MakeBox(*dimensions).Shape())
    raw=path.with_name('two-products.step');writer=STEPControl_Writer();writer.Transfer(compound,STEPControl_ShellBasedSurfaceModel);writer.Write(str(raw))
    with CadDocument.from_step(raw,workers=1) as document:
        ix,model=document.index,document.model
        (body,rep),(other,_) = model.bodies
        product=model.rep_product[rep]
        shell=int(ix.refs_of(other)[0]);first=int(ix.refs_of(body)[0])
        splitter=Splitter(ix,model);mask,rewritten=splitter.closure_products([product])
        mask=forward_closure(ix,[ix.r(shell)],mask)
        rewritten[body]=f"#{int(ix.ids[body])}=SHELL_BASED_SURFACE_MODEL('',(#{first},#{shell}));".encode()
        # An explicit face override plus body fill exercises inherited appearance
        # through the new nested assembly, with no artificial display palette.
        target=int(ix.ids[model.body_faces(body)[0]])
        start=ix.max_id+1;extra=[]
        for color,face in [((.2,.3,.4),int(ix.ids[body])),((1.,0.,0.),target)]:
            ids=list(range(start,start+8));start+=8
            extra.extend([f"#{ids[0]}=COLOUR_RGB('literal #123',{color[0]},{color[1]},{color[2]});",
                f"#{ids[1]}=FILL_AREA_STYLE_COLOUR('',#{ids[0]});",f"#{ids[2]}=FILL_AREA_STYLE('',(#{ids[1]}));",
                f"#{ids[3]}=SURFACE_STYLE_FILL_AREA(#{ids[2]});",f"#{ids[4]}=SURFACE_SIDE_STYLE('',(#{ids[3]}));",
                f"#{ids[5]}=SURFACE_STYLE_USAGE(.BOTH.,#{ids[4]});",f"#{ids[6]}=PRESENTATION_STYLE_ASSIGNMENT((#{ids[5]}));",
                f"#{ids[7]}=STYLED_ITEM('',(#{ids[6]}),#{face});"])
        splitter.write_closure(mask,rewritten,path,extra=[s.encode() for s in extra])


class HierarchyTests(unittest.TestCase):
    def test_reference_rewrite_respects_strings_and_comments(self):
        self.assertEqual(remap_record(b"#1=THING('literal #2 and ''#1''',#2);/* #1 */",{1:101,2:202}),
                         b"#101=THING('literal #2 and ''#1''',#202);/* #1 */")

    def test_native_nested_shell_parts_instances_and_source_styles(self):
        from mesh_parts import tessellate
        from validate_parts import read_part
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.step';shell_fixture(source)
            with CadDocument.from_step(source,workers=1) as document:
                ix,model=document.index,document.model
                pid=int(ix.ids[next(iter(model.product_name))]);body=model.bodies[0][0]
                shells=list(map(int,ix.refs_of(body)))
                policy={'schema_version':1,'source_sha256':document.source_sha256,'product_names':{str(pid):'fixture'},'groups':[]}
                motion={'schema_version':1,'source_sha256':document.source_sha256,'assignments':[]}
                catalog=build_catalog(document,policy,motion)
                second={**catalog['occurrences'][0],'occurrence_path':[999]}
                matrix=np.eye(4);matrix[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]];matrix[:3,3]=[1000,2000,3000]
                second['source_world_matrix']=matrix.tolist();catalog['occurrences'].append(second)
                partition=compile_partition(document,catalog,{'schema_version':1,'source_sha256':document.source_sha256,'length_unit':'millimetre',
                    'products':[{'product_id':pid,'name':'fixture','fallback_group':'fixture/shared','shell_rules':[
                        {'id':name,'body_id':int(ix.ids[body]),'group':'fixture/panels/'+name,'priority':1,'shell_ids':[shell],'evidence':['fixture']}
                        for shell,name in zip(shells,['left','right'])]}]})
                report=write_hierarchy(document,catalog,[partition],[],{'name':'field','secondary_product_ids':[],'equipment_product_ids':[]},root/'export')
                self.assertTrue(report['source_geometry_preserved'])
                self.assertEqual(report['work_part_definitions'],2)
                self.assertEqual(report['expected_placed_faces'],24)
                self.assertEqual(report['source_face_definitions'],12)
                changed_occurrences=[dict(o) for o in report['source_occurrences']]
                bad_matrix=np.eye(4);bad_matrix[0,3]=777
                changed_occurrences[0]['source_world_matrix']=bad_matrix.tolist()
                with self.assertRaisesRegex(ValueError,'placement changed'):
                    verify_source_placements(report['assemblies'],report['root_product_id'],
                                             report['source_product_definitions'],changed_occurrences)
                self.assertEqual(len({c['export_body_ids'][str(int(ix.ids[body]))] for c in report['components']}),2)
                with CadDocument.from_step(root/'export/field.step',workers=1) as exported:
                    self.assertEqual(len(exported.model.bodies),2)
                    self.assertEqual(len(exported.index.rows_of('SHELL_BASED_SURFACE_MODEL')),2)
                    self.assertTrue({'left','right','panels','fixture','terrain','field'} <= set(exported.model.product_name.values()))
                    self.assertGreater(verify_assembly_graph(exported.index,report['assemblies']),0)
                    changed=[{**a,'children':[dict(c) for c in a['children']]} for a in report['assemblies']]
                    changed[-1]['children'][0]['product_id']=-1
                    with self.assertRaisesRegex(ValueError,'pose changed'):
                        verify_assembly_graph(exported.index,changed)
                original,_,error=read_part(str(source));self.assertIsNone(error)
                full,_,error=read_part(str(root/'export/field.step'));self.assertIsNone(error)
                def colors(doc):
                    _,_,indices,keys=tessellate(doc,.4,.25)
                    return Counter(keys[int(i)] for i in indices)
                expected=colors(original);actual=colors(full)
                self.assertNotIn(None,expected)
                self.assertEqual(actual,Counter({k:v*2 for k,v in expected.items()}))
                native=native_validate(root/'export')
                self.assertEqual(native['native_faces'],24)
                document.verify_source()


if __name__=='__main__':unittest.main()
