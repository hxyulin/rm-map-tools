# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from gltf_scene import accessor, read_glb, write_glb, scene_nodes
from simplify_package import append_accessor, scene_triangles
from test_cad_planar_panels import grid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('refine_panels', ROOT / 'benchmarks/2026-10-23-runtime-opportunities/refine.py')
refine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refine)


def fixture(path, *, separate_parts=False, red=False, mirrored=False, shared=False):
    g = grid(2, 2)
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'name': 'scope', 'extras': {'component_id': 'test/panel'}, 'children': [1, 2]},
                     {'name': 'left', 'mesh': 0}, {'name': 'right', 'mesh': 0, 'translation': [.04, 0, 0]}],
           'meshes': [], 'accessors': [], 'bufferViews': [], 'buffers': [{'byteLength': 0}],
           'materials': [{'pbrMetallicRoughness': {'baseColorFactor': ([1, 0, 0, 1] if red else [.1, .1, .1, 1])},
                          'extras': {'step_colour_srgb': ([1, 0, 0] if red else [.2, .2, .2])}}]}
    if separate_parts:
        for i in (1, 2):doc['nodes'][i]['extras'] = {'rm': {'part_id': 'part-' + str(i)}}
    if mirrored:
        doc['nodes'][2]['scale'] = [-1, 1, 1]
        doc['nodes'][2]['translation'] = [.08, 0, 0]
    binary = bytearray()
    positions = np.ascontiguousarray(g.reshape(-1, 3) / 1000, dtype='<f4')
    normals = np.tile(np.array([0, 0, 1], dtype='<f4'), (len(positions), 1))
    prim = {'attributes': {'POSITION': append_accessor(doc, binary, positions, 'VEC3', 5126),
                           'NORMAL': append_accessor(doc, binary, normals, 'VEC3', 5126)},
            'indices': append_accessor(doc, binary, np.arange(len(positions), dtype=np.uint32), 'SCALAR', 5125), 'material': 0}
    doc['meshes'] = [{'primitives': [prim]}]
    if not shared:
        doc['meshes'].append({'primitives': [prim]})
        doc['nodes'][2]['mesh'] = 1
    doc['buffers'][0]['byteLength'] = len(binary)
    write_glb(path, doc, binary)


class PlanarExportTests(unittest.TestCase):
    def run_case(self, **options):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source.glb', Path(directory) / 'target.glb'
            fixture(source, **options)
            original = source.read_bytes()
            row = refine.refine_asset(source, source, target)
            doc, blob = read_glb(target)
            self.assertEqual(source.read_bytes(), original)
            return row, doc, blob

    def test_adjacent_independent_meshes_become_single_rectangle(self):
        row, doc, blob = self.run_case()
        self.assertEqual(row['before'], 16)
        self.assertEqual(row['after'], 2)
        self.assertEqual(len(row['groups']), 1)
        self.assertEqual(row['groups'][0]['source_nodes'], [1, 2])
        self.assertEqual(len(doc['nodes']), 4)
        self.assertNotIn('mesh', doc['nodes'][1])

    def test_existing_mesh_sharing_is_retained(self):
        row, doc, blob = self.run_case(shared=True)
        self.assertEqual(row['after'], 4)
        self.assertEqual(len(row['groups']), 2)
        children = [n for n in doc['nodes'][3:] if 'mesh' in n]
        self.assertEqual(children[0]['mesh'], children[1]['mesh'])

    def test_source_part_boundaries_prevent_cross_part_merge(self):
        row, doc, blob = self.run_case(separate_parts=True)
        self.assertEqual(row['after'], 4)
        self.assertEqual(len(row['groups']), 2)
        self.assertEqual(doc['nodes'][1]['extras']['rm']['part_id'], 'part-1')

    def test_chromatic_mesh_is_untouched(self):
        row, doc, blob = self.run_case(red=True)
        self.assertEqual(row['before'], row['after'])
        self.assertEqual(len(doc['nodes']), 3)
        self.assertEqual(len(row['groups']), 0)

    def test_mirrored_instance_retains_coverage_and_winding(self):
        row, doc, blob = self.run_case(mirrored=True)
        self.assertLess(row['after'], row['before'])
        prim = doc['meshes'][doc['nodes'][-1]['mesh']]['primitives'][0]
        p = accessor(doc, blob, prim['attributes']['POSITION'])
        f = accessor(doc, blob, prim['indices']).reshape(-1, 3)
        self.assertAlmostEqual(float(p[:, 0].max()), .08, places=6)
        self.assertTrue(np.all(np.cross(p[f][:, 1] - p[f][:, 0], p[f][:, 2] - p[f][:, 0])[:, 2] > 0))


if __name__ == '__main__':
    unittest.main()
