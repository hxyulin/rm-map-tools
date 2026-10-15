"""Regression for Creo's property-only duplicate surface representations."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from p21index import build_index, Index
from p21model import Model
from p21split import Splitter

FIXTURE = r"""ISO-10303-21;
HEADER;
ENDSEC;
DATA;
#1=PRODUCT('surface','surface','',(#4));
#2=PRODUCT_DEFINITION_FORMATION('','',#1);
#3=PRODUCT_DEFINITION('','',#2,$);
#4=PRODUCT_CONTEXT('','part definition',$);
#5=PRODUCT_DEFINITION_SHAPE('','',#3);
#6=SHELL_BASED_SURFACE_MODEL('',(#7));
#7=OPEN_SHELL('',(#8));
#8=ADVANCED_FACE('',(),$,.T.);
#9=SHAPE_DEFINITION_REPRESENTATION(#5,#10);
#10=MANIFOLD_SURFACE_SHAPE_REPRESENTATION('',(#6),$);
#11=SHAPE_REPRESENTATION('',(#6),$);
ENDSEC;
END-ISO-10303-21;
"""


class SharedRepresentationTests(unittest.TestCase):
    def test_duplicate_representation_keeps_surface_owned_and_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'surface.stp'
            source.write_text(FIXTURE)
            index = Path(tmp) / 'surface.npz'
            np.savez(index, **build_index(str(source), workers=1))
            ix = Index(index)
            model = Model(ix)
            body = ix.r(6)
            self.assertEqual(model.bodies, [(body, ix.r(10))])
            self.assertEqual(model.body_rep[body], ix.r(10))
            mask, _ = Splitter(ix, model).closure_products([ix.r(1)])
            self.assertTrue(mask[body])
            ix.mm.close()
            ix._f.close()


if __name__ == '__main__':
    unittest.main()
