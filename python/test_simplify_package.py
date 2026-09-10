# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from export_field_package import GlbWriter
from gltf_scene import accessor, read_glb, write_glb
from simplify_package import simplify_mesh, simplify_glb, read_config
from mesh_quality import deviation


def grid(size=12):
    points = np.array([[x / size, y / size, 0] for y in range(size + 1) for x in range(size + 1)], dtype=np.float32)
    triangles = []
    for y in range(size):
        for x in range(size):
            if size // 3 <= x < 2 * size // 3 and size // 3 <= y < 2 * size // 3: continue
            a = y * (size + 1) + x
            triangles += [(a, a + 1, a + size + 2), (a, a + size + 2, a + size + 1)]
    return points, np.asarray(triangles)


def border_edges(points, triangles):
    edges = np.sort(np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    return {tuple(sorted(tuple(float(v) for v in p) for p in points[e])) for e in edges[counts == 1]}


class SimplificationTests(unittest.TestCase):
    def test_dense_sampling_detects_a_local_deviation_sparse_sampling_misses(self):
        points, triangles = grid(64)
        sparse = triangles[np.linspace(0, len(triangles) - 1, 96, dtype=int)]
        dense = triangles[np.linspace(0, len(triangles) - 1, 1024, dtype=int)]
        vertex = next(int(t[0]) for t in dense if t[0] not in sparse)
        raised = points.copy()
        raised[vertex, 2] = .01
        self.assertLess(deviation(raised, triangles, points, triangles, count=96)['max'], 1e-6)
        self.assertGreater(deviation(raised, triangles, points, triangles, count=1024)['max'], .009)

    def test_deviation_sample_budget_requires_bounded_integer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            config = {'schema_version': 1, 'input': 'source', 'output': 'result',
                      'defaults': {'visual_error_mm': 2, 'collision_error_mm': 2}}
            for value in (True, 0, 95, 1024.5, 16385):
                config['defaults']['deviation_samples'] = value
                path.write_text(json.dumps(config))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    read_config(path)
            config['defaults']['deviation_samples'] = 1024
            path.write_text(json.dumps(config))
            self.assertEqual(read_config(path)['defaults']['deviation_samples'], 1024)

    def test_open_hole_and_outer_border_remain_exact(self):
        points, triangles = grid()
        simplified, faces, error = simplify_mesh(points, triangles, 0.001)
        self.assertLess(len(faces), len(triangles) // 2)
        self.assertEqual(border_edges(points, triangles), border_edges(simplified, faces))
        self.assertLessEqual(error, 0.001)

    def test_unlocked_planar_borders_reduce_more_without_filling_the_hole(self):
        points, triangles = grid()
        _, locked, _ = simplify_mesh(points, triangles, .001)
        simplified, faces, _ = simplify_mesh(points, triangles, .001, lock_borders=False)
        self.assertLess(len(faces), len(locked) // 2)
        # The flat ring retains its area: relaxed edges may lose subdivisions,
        # but this fixture's central opening must not be filled.
        def area(p, t):
            a = p[t]
            return np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1).sum() / 2
        self.assertAlmostEqual(float(area(points, triangles)), float(area(simplified, faces)), places=6)
        self.assertLess(deviation(points, triangles, simplified, faces, count=1024)['max'], 1e-6)

    def test_disconnected_tiny_detail_is_not_dropped(self):
        points, triangles = grid()
        tetra = np.array([[2, 2, 0], [2.00001, 2, 0], [2, 2.00001, 0], [2, 2, 0.00001]])
        faces = np.array([[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]])
        triangles = np.vstack([triangles, faces + len(points)])
        points = np.vstack([points, tetra])
        for locked in (True, False):
            p, t, _ = simplify_mesh(points, triangles, 0.005, lock_borders=locked)
            self.assertTrue(np.any(np.all(p[t][:, :, 0] > 1.5, axis=1)))

    def test_bound_nodes_surface_and_material_indices_survive_compaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.glb'
            p, t = grid()
            writer = GlbWriter('root', {'version': '2.0'})
            writer.add_node('panel', p, t, ['1,1,1'] * len(t))
            writer.add_node('light', p + [0, 0, 1], t, ['1,0,0'] * len(t))
            writer.write(path)
            doc, binary = read_glb(path)
            doc['nodes'][1]['extras'] = {'rm': {'id': 'panel', 'roles': ['unclassified']}}
            doc['nodes'][2]['extras'] = {'rm': {'id': 'light', 'roles': ['led_surface']}}
            doc['nodes'][1]['translation'] = [3, 4, 5]
            surface = {'id': 'paint', 'roles': ['unclassified']}
            doc['meshes'][0]['primitives'][0]['extras'] = {'rm': surface}
            # An unused clone should be pruned, not uploaded at startup.
            doc['meshes'].append(copy.deepcopy(doc['meshes'][0]))
            write_glb(path, doc, binary)
            binding = {'nodes': [{'node': i, 'metadata': doc['nodes'][i]['extras']['rm']} for i in (1, 2)],
                       'surfaces': [{'node': 1, 'primitive': 0, 'metadata': surface}]}
            original_light = copy.deepcopy(doc['meshes'][1]['primitives'][0])
            original_points = accessor(doc, binary, original_light['attributes']['POSITION']).copy()
            report = simplify_glb(path, 0.5, binding, lock_borders=False)
            after, buf = read_glb(path)
            self.assertEqual(after['nodes'], doc['nodes'])
            self.assertEqual(after['materials'], doc['materials'])
            self.assertEqual(len(after['meshes']), 2)
            light = after['meshes'][1]['primitives'][0]
            np.testing.assert_array_equal(accessor(after, buf, light['attributes']['POSITION']), original_points)
            self.assertLess(report['after_triangles'], report['before_triangles'])
            self.assertLess(report['after_bytes'], report['before_bytes'])
            self.assertEqual(report['method'], 'meshopt-boundary-simplification-v1')
            self.assertFalse(report['open_borders_locked'])
            self.assertGreaterEqual(report['deviation_triangles_per_direction'], 1024)

    def test_unlocked_boundaries_reject_sparse_checks_and_non_boolean_policy(self):
        with self.assertRaisesRegex(ValueError, 'at least 1024'):
            simplify_glb(Path('not-read.glb'), 1, lock_borders=False, deviation_samples=96)
        with self.assertRaisesRegex(ValueError, 'boolean'):
            simplify_glb(Path('not-read.glb'), 1, lock_borders='false')

    def test_explicit_artwork_selection_is_preserved_and_unknown_names_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'art.glb'
            points, triangles = grid()
            writer = GlbWriter('root', {'version': '2.0'})
            writer.add_node('wordmark', points, triangles, [None] * len(triangles))
            writer.write(path)
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'one live mesh node'):
                simplify_glb(path, 4, lock_borders=False,
                             preserve=[{'node': 'missing', 'primitive': 0}])
            self.assertEqual(path.read_bytes(), original)
            before, blob = read_glb(path)
            report = simplify_glb(path, 4, lock_borders=False,
                                  preserve=[{'node': 'wordmark', 'primitive': 0}])
            after, data = read_glb(path)
            old = before['meshes'][0]['primitives'][0]
            new = after['meshes'][0]['primitives'][0]
            np.testing.assert_array_equal(accessor(before, blob, old['attributes']['POSITION']),
                                          accessor(after, data, new['attributes']['POSITION']))
            self.assertEqual(report['before_triangles'], report['after_triangles'])
            self.assertEqual(report['primitives'][0]['kept'], 'explicit_preservation')

    def test_unlocked_search_avoids_restoring_a_whole_tiny_component(self):
        # At a very coarse error this closed sphere disappears and is restored
        # by the component safeguard. A finer candidate retains a cheap mesh.
        points = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                           [0, 0, 1], [0, 0, -1]], dtype=float)
        triangles = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
                              [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]])
        for _ in range(2):
            vertices, cache, faces = points.tolist(), {}, []
            def midpoint(a, b):
                key = tuple(sorted((a, b)))
                if key not in cache:
                    point = points[a] + points[b]
                    point /= np.linalg.norm(point)
                    cache[key] = len(vertices)
                    vertices.append(point.tolist())
                return cache[key]
            for a, b, c in triangles:
                ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
                faces.extend([[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]])
            points, triangles = np.array(vertices), np.array(faces)
        points *= .001
        _, coarse, _ = simplify_mesh(points, triangles, .004, lock_borders=False)
        self.assertEqual(len(coarse), len(triangles))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tiny.glb'
            writer = GlbWriter('root', {'version': '2.0'})
            writer.add_node('tiny', points, triangles, [None] * len(triangles))
            writer.write(path)
            report = simplify_glb(path, 4, sampled_limit_mm=12, lock_borders=False)
            self.assertGreater(report['after_triangles'], 0)
            self.assertLess(report['after_triangles'], len(coarse) // 4)

    def test_invalid_semantic_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.glb'
            p, t = grid()
            writer = GlbWriter('root', {'version': '2.0'})
            writer.add_node('panel', p, t, [None] * len(t))
            writer.write(path)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                simplify_glb(path, .5, {'nodes': [{'node': 1, 'metadata': {'id': 'wrong'}}]})
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__': unittest.main()
