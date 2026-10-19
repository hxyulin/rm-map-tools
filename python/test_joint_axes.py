# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-native cylinder evidence and OCCT ordinal ownership."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from audit_joint_axes import audit


@unittest.skipUnless(importlib.util.find_spec('OCP'),'native OCCT audit requires OCP')
class JointAxesTests(unittest.TestCase):
    def test_cylinder_axis_ownership_bounds_and_source_bytes_are_preserved(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cylinder.step';writer=STEPControl_Writer()
            writer.Transfer(BRepPrimAPI_MakeCylinder(10.,20.).Shape(),STEPControl_AsIs)
            self.assertEqual(writer.Write(str(path)),IFSelect_RetDone)
            original=path.read_bytes();report=audit(path)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(report['source_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(report['counts'],dict(solid=1,shell=1,face=3))
            self.assertEqual(len(report['cylinders']),1)
            c=report['cylinders'][0]
            self.assertEqual(c['solid'],1);self.assertEqual(c['shell'],1)
            np.testing.assert_allclose(c['axis'],[0,0,1],atol=1e-10)
            np.testing.assert_allclose(c['line_mm'],[0,0,0],atol=1e-10)
            np.testing.assert_allclose(c['bounds_mm'],[-10,-10,0,10,10,20],atol=1e-6)
            self.assertEqual(audit(path,11.)['cylinders'],[])

if __name__=='__main__':unittest.main()
