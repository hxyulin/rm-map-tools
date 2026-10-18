# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native planar caps must preserve outer boundaries and functional apertures."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from referee_hardware import close_small_planar_holes,face_arrays,export_model


class HardwareTests(unittest.TestCase):
    def panel(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeEdge
        from OCP.gp import gp_Pnt,gp_Circ,gp_Ax2,gp_Dir
        wire=BRepBuilderAPI_MakePolygon()
        for p in [(0,0,0),(100,0,0),(100,100,0),(0,100,0)]:wire.Add(gp_Pnt(*p))
        wire.Close();face=BRepBuilderAPI_MakeFace(wire.Wire())
        for x,r in [(20,2),(60,15)]:
            hole=BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(x,50,0),gp_Dir(0,0,1)),r)).Edge()).Wire()
            hole.Reverse();face.Add(hole)
        return face.Face()

    def test_small_hole_cap_preserves_large_bore_area_and_planarity(self):
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        original=self.panel();coarse,count=close_small_planar_holes(original,8)
        self.assertEqual(count,1)
        old,new=GProp_GProps(),GProp_GProps()
        BRepGProp.SurfaceProperties_s(original,old);BRepGProp.SurfaceProperties_s(coarse,new)
        self.assertAlmostEqual(new.Mass()-old.Mass(),np.pi*4,places=7)
        self.assertAlmostEqual(new.Mass(),10000-np.pi*225,places=7)
        p,t=face_arrays(coarse,.25,.35)
        np.testing.assert_allclose(p[:,2],0,atol=1e-12)
        np.testing.assert_allclose([p.min(0),p.max(0)],[[0,0,0],[100,100,0]],atol=1e-9)
        centers=p[t].mean(1)
        self.assertTrue(np.all(np.linalg.norm(centers[:,:2]-[60,50],axis=1)>14.5))
        self.assertEqual(close_small_planar_holes(coarse,8)[1],0)

    def test_rough_hulls_prune_enclosed_detail_but_preserve_open_passage(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir
        from OCP.TDocStd import TDocStd_Document
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.TopoDS import TopoDS_Compound
        from OCP.BRep import BRep_Builder
        from referee_hardware import rough_mesh
        tube=BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(40,40,80).Shape(),
            BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(20,20,-1),gp_Dir(0,0,1)),10,82).Shape()).Shape()
        shapes=[tube,BRepPrimAPI_MakeBox(gp_Pnt(80,0,0),30,30,30).Shape(),
            BRepPrimAPI_MakeBox(gp_Pnt(85,5,5),15,15,15).Shape(),
            BRepPrimAPI_MakeBox(gp_Pnt(120,0,0),2,2,4).Shape(),
            BRepPrimAPI_MakeBox(gp_Pnt(140,0,0),80,5,5).Shape()]
        root=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(root)
        for shape in shapes:builder.Add(root,shape)
        doc=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
        XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(root,False)
        (p,t,c),report=rough_mesh(doc,None,{'detail_error_mm':1.5,'omit_detail_span_mm':12,
            'tessellation_linear_mm':.25,'tessellation_angular_rad':.35},{'preserve_shape_solids':[1,4],'omit_cable_solids':[5]})
        self.assertIn(1,report['retained_solids']);self.assertIn(2,report['retained_solids'])
        self.assertNotIn(3,report['retained_solids']);self.assertIn(4,report['retained_solids'])
        self.assertNotIn(5,report['retained_solids'])
        self.assertIn({'solid':5,'reason':'user-approved cable omission'},report['removed_solids'])
        self.assertLess(p[:,0].max(),130)
        row=next(r for r in report['triangle_ranges'] if r['solid']==1)
        tri=p[t[row['triangle_start']:row['triangle_start']+row['triangle_count']]][:,:,:2]-[20,20]
        a,b,d=tri[:,0],tri[:,1],tri[:,2]
        cross=lambda x,y:x[:,0]*y[:,1]-x[:,1]*y[:,0]
        area=cross(b-a,d-a);mask=abs(area)>1e-8
        u=cross(b[mask],d[mask])/area[mask];v=cross(d[mask],a[mask])/area[mask];w=1-u-v
        self.assertFalse(np.any((u>=0)&(v>=0)&(w>=0)), 'rough mesh capped the projectile passage')

    def test_source_checksum_rejected_before_loading_or_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'model.step';source.write_text('not CAD')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                export_model(source,{'sha256':'0'*64,'id':'test'}, {},Path(folder))
            self.assertEqual([p.name for p in Path(folder).iterdir()],['model.step'])

if __name__=='__main__':unittest.main()
