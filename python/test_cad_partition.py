# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Whole-shell separation preserves source topology, style bindings and full coverage."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from cad_document import CadDocument
from cad_components import build_catalog, export_selection
from cad_partition import compile_partition, _selection, _pack_step, _validate_mesh_stats
from test_cad_document import FIXTURE


class PartitionTests(unittest.TestCase):
    @contextmanager
    def document(self, solid=False, voids=False):
        text = FIXTURE.replace("#6=SHELL_BASED_SURFACE_MODEL('',(#7));", "#6=SHELL_BASED_SURFACE_MODEL('',(#7,#27));")
        text = text.replace('ENDSEC;\nEND-ISO', """
#27=OPEN_SHELL('',(#28));
#28=ADVANCED_FACE('',(),$,.T.);
#29=STYLED_ITEM('',(#18),#6);
#90=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
#91=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNIT_ASSIGNED_CONTEXT((#90))REPRESENTATION_CONTEXT('',''));
ENDSEC;
END-ISO""")
        if solid:
            text = text.replace("#6=SHELL_BASED_SURFACE_MODEL('',(#7,#27));", "#6=MANIFOLD_SOLID_BREP('',#7);")
            text = text.replace("#7=OPEN_SHELL('',(#8));", "#7=CLOSED_SHELL('',(#8,#28));")
        if voids:
            text = text.replace("#6=SHELL_BASED_SURFACE_MODEL('',(#7,#27));",
                                "#6=BREP_WITH_VOIDS('',#7,(#39));")
            text = text.replace('=OPEN_SHELL(', '=CLOSED_SHELL(')
            text = text.replace('ENDSEC;\nEND-ISO',
                                "#39=ORIENTED_CLOSED_SHELL('',*,#27,.F.);\nENDSEC;\nEND-ISO")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.step'
            path.write_text(text)
            with CadDocument.from_step(path, workers=1) as doc:
                yield doc
                self.assertEqual(path.read_text(), text)
                self.assertIsNone(doc._working)

    def catalog(self, doc):
        policy = {'schema_version': 1, 'source_sha256': doc.source_sha256,
                  'product_names': {'1': 'part'}, 'groups': []}
        motion = {'schema_version': 1, 'source_sha256': doc.source_sha256, 'assignments': []}
        return build_catalog(doc, policy, motion)

    def policy(self, doc):
        return {'schema_version': 1, 'source_sha256': doc.source_sha256, 'length_unit': 'millimetre',
                'products': [{'name': 'part', 'product_id': 1, 'fallback_group': 'part/remainder',
                              'shell_rules': [{'id': 'first', 'body_id': 6, 'group': 'part/first',
                                               'priority': 1, 'shell_ids': [7], 'evidence': ['fixture']}]}]}

    def test_shell_partition_covers_every_face_once_and_keeps_unmatched_shell(self):
        with self.document() as doc:
            result = compile_partition(doc, self.catalog(doc), self.policy(doc))['products'][0]
            self.assertEqual(result['source_face_count'], 2)
            self.assertEqual(result['source_shell_count'], 2)
            self.assertTrue(result['coverage_exactly_once'])
            self.assertEqual([g['face_ids'] for g in result['groups']], [[8], [28]])
            self.assertEqual(result['assignments']['unmatched-source-shell'], 1)

    def test_equal_priority_conflict_is_retained_and_higher_priority_resolves_it(self):
        with self.document() as doc:
            policy = self.policy(doc)
            rules = policy['products'][0]['shell_rules']
            rules.append({**rules[0], 'id': 'second', 'group': 'part/second'})
            result = compile_partition(doc, self.catalog(doc), policy)['products'][0]
            self.assertEqual(result['assignments']['equal-priority-shell-conflict'], 1)
            self.assertEqual(result['groups'][0]['face_count'], 2)
            rules[1]['priority'] = 2
            result = compile_partition(doc, self.catalog(doc), policy)['products'][0]
            chosen = next(u for u in result['units'] if u['shell_id'] == 7)
            self.assertEqual(chosen['group'], 'part/second')

    def test_filtered_shell_export_preserves_face_and_parent_styles_and_compresses_losslessly(self):
        with self.document() as doc, tempfile.TemporaryDirectory() as tmp:
            catalog = self.catalog(doc)
            group = compile_partition(doc, catalog, self.policy(doc))['products'][0]['groups'][0]
            selection = _selection(catalog, 1, group)
            out = Path(tmp)/'first'
            export_selection(doc, selection, out, shell_ids_by_body={6: [7]})
            original = (out/'source.step').read_bytes()
            with CadDocument.from_step(out/'source.step', workers=1) as check:
                self.assertEqual(check.entity(6).reference_ids.tolist(), [7])
                self.assertEqual(check.index.rows_of('ADVANCED_FACE').size, 1)
                for source in [7, 8, 12, 19, 29]:
                    self.assertEqual(check.entity(source).raw, doc.entity(source).raw)
                self.assertEqual(check.index.r(27), -1)
                self.assertNotEqual(check.entity(6).raw, doc.entity(6).raw)
            _pack_step(out)
            import gzip
            self.assertEqual(gzip.decompress((out/'source.step.gz').read_bytes()), original)
            self.assertFalse((out/'source.step').exists())

    def test_unknown_empty_and_duplicate_shell_selection_cannot_export(self):
        with self.document() as doc, tempfile.TemporaryDirectory() as tmp:
            catalog = self.catalog(doc)
            group = compile_partition(doc, catalog, self.policy(doc))['products'][0]['groups'][0]
            selection = _selection(catalog, 1, group)
            for shells in ([], [999], [7, 7]):
                with self.assertRaisesRegex(ValueError, 'subset'):
                    export_selection(doc, selection, Path(tmp)/'bad', shell_ids_by_body={6: shells})
                self.assertFalse((Path(tmp)/'bad').exists())

    def test_face_patch_keeps_exact_faces_and_styles_as_explicit_open_surfaces(self):
        with self.document() as doc, tempfile.TemporaryDirectory() as tmp:
            catalog = self.catalog(doc)
            group = compile_partition(doc, catalog, self.policy(doc))['products'][0]['groups'][0]
            selection = _selection(catalog, 1, group)
            out = Path(tmp)/'patch'
            export_selection(doc, selection, out, face_ids_by_body={6: [8]})
            with CadDocument.from_step(out/'source.step', workers=1) as check:
                self.assertEqual(check.index.rows_of('ADVANCED_FACE').size, 1)
                self.assertEqual(check.entity(8).raw, doc.entity(8).raw)
                self.assertEqual(check.entity(29).raw, doc.entity(29).raw)
                self.assertEqual(check.index.tname(check.index.r(7)), 'OPEN_SHELL')
                self.assertEqual(check.index.r(27), -1)
                self.assertEqual(check.index.r(28), -1)
            import json
            metadata = json.loads((out/'selection.json').read_text())
            self.assertEqual(metadata['selected_source_face_ids_by_body'], {'6': [8]})
            self.assertIn('open surfaces', metadata['face_patch_topology'])

    def test_solid_face_patch_changes_only_container_topology(self):
        from cad_components import select_components
        with self.document(solid=True) as doc, tempfile.TemporaryDirectory() as tmp:
            selection = select_components(self.catalog(doc), 'p1.b6')
            out = Path(tmp)/'solid-patch'
            export_selection(doc, selection, out, face_ids_by_body={6: [8]})
            with CadDocument.from_step(out/'source.step', workers=1) as check:
                self.assertEqual(doc.index.tname(doc.index.r(6)), 'MANIFOLD_SOLID_BREP')
                self.assertEqual(check.index.tname(check.index.r(6)), 'SHELL_BASED_SURFACE_MODEL')
                self.assertEqual(check.index.tname(check.index.r(7)), 'OPEN_SHELL')
                self.assertEqual(check.entity(8).raw, doc.entity(8).raw)
                self.assertEqual(check.entity(29).raw, doc.entity(29).raw)
                self.assertEqual(check.index.r(28), -1)

    def test_invalid_or_combined_face_and_shell_selectors_are_rejected(self):
        with self.document() as doc, tempfile.TemporaryDirectory() as tmp:
            catalog = self.catalog(doc)
            group = compile_partition(doc, catalog, self.policy(doc))['products'][0]['groups'][0]
            selection = _selection(catalog, 1, group)
            for faces in ([], [999], [8, 8]):
                with self.assertRaisesRegex(ValueError, 'subset'):
                    export_selection(doc, selection, Path(tmp)/'bad', face_ids_by_body={6: faces})
            with self.assertRaisesRegex(ValueError, 'unfiltered'):
                export_selection(doc, selection, Path(tmp)/'bad',
                                 face_ids_by_body={6: [8]}, shell_ids_by_body={6: [7]})

    def test_explicit_body_rules_override_groups_and_reject_ambiguous_ownership(self):
        with self.document(solid=True) as doc:
            policy = self.policy(doc)
            spec = policy['products'][0]
            spec['shell_rules'] = []
            rule = {'body_ids': [6], 'group': 'part/solid', 'evidence': ['source fixture']}
            spec['body_rules'] = [rule]
            product = compile_partition(doc, self.catalog(doc), policy)['products'][0]
            self.assertEqual(product['groups'][0]['id'], 'part/solid')
            self.assertEqual(product['groups'][0]['face_ids'], [8, 28])
            self.assertEqual(product['assignments'], {'explicit-body-rule': 1})
            spec['body_rules'].append(dict(rule))
            with self.assertRaisesRegex(ValueError, 'multiple body rules'):
                compile_partition(doc, self.catalog(doc), policy)
            for bad in ([999], [6, 6], []):
                spec['body_rules'] = [{**rule, 'body_ids': bad}]
                with self.assertRaisesRegex(ValueError, 'distinct original'):
                    compile_partition(doc, self.catalog(doc), policy)
            spec['body_rules'] = [{**rule, 'evidence': []}]
            with self.assertRaisesRegex(ValueError, 'evidence'):
                compile_partition(doc, self.catalog(doc), policy)

    def test_body_rules_cannot_swallow_surface_shell_partitioning(self):
        with self.document() as doc:
            policy = self.policy(doc)
            policy['products'][0]['body_rules'] = [
                {'body_ids': [6], 'group': 'part/invalid', 'evidence': ['fixture']}]
            with self.assertRaisesRegex(ValueError, 'non-surface'):
                compile_partition(doc, self.catalog(doc), policy)

    def test_mesh_validation_accepts_only_measured_zero_area_degeneracy(self):
        _validate_mesh_stats({})
        _validate_mesh_stats({'degenerate_faces': 1,
                              'degenerate_details': [{'area_mm2': 0.0}]})
        for stats in [
            {'unmeshed_faces': 1},
            {'degenerate_faces': 1},
            {'degenerate_faces': 2, 'degenerate_details': [{'area_mm2': 0.0}]},
            {'degenerate_faces': 1, 'degenerate_details': [{'area_mm2': 1e-8}]},
            {'degenerate_faces': 1, 'degenerate_details': [{'area_mm2': float('nan')}]},
            {'degenerate_faces': 1, 'degenerate_details': [{'area_mm2': float('inf')}]},
        ]:
            with self.assertRaises(ValueError):
                _validate_mesh_stats(stats)

    def test_source_unit_mode_keeps_solid_cavities_and_separates_surface_shells(self):
        for voids in [False, True]:
            with self.document(voids=voids) as doc:
                policy = self.policy(doc)
                spec = policy['products'][0]
                spec['shell_rules'] = []
                spec['split_source_units'] = True
                product = compile_partition(doc, self.catalog(doc), policy)['products'][0]
                groups = {g['id']: g['face_ids'] for g in product['groups']}
                if voids:
                    self.assertEqual(groups, {'part/body-6': [8, 28]})
                    self.assertEqual(product['assignments'], {'original-solid-body': 1})
                else:
                    self.assertEqual(groups, {'part/shell-7': [8], 'part/shell-27': [28]})
                    self.assertEqual(product['assignments'], {'original-surface-shell': 2})

    def test_source_unit_mode_rejects_non_boolean_and_mixed_grouping(self):
        with self.document() as doc:
            for value in [1, 'true', None]:
                policy = self.policy(doc)
                policy['products'][0]['split_source_units'] = value
                with self.assertRaisesRegex(ValueError, 'source-unit mode'):
                    compile_partition(doc, self.catalog(doc), policy)
            for key, value in [('shell_rules', [{'id': 'unused'}]),
                               ('body_rules', [{'body_ids': [6]}]),
                               ('body_group_overrides', {'part/other-bodies': 'part/mixed'})]:
                policy = self.policy(doc)
                spec = policy['products'][0]
                spec['shell_rules'] = []
                spec['split_source_units'] = True
                spec[key] = value
                with self.assertRaisesRegex(ValueError, 'source-unit mode'):
                    compile_partition(doc, self.catalog(doc), policy)

    def test_stale_and_wrong_source_shell_rules_are_rejected(self):
        with self.document() as doc:
            policy = self.policy(doc)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                compile_partition(doc, self.catalog(doc), {**policy, 'source_sha256': 'stale'})
            catalog = self.catalog(doc)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                compile_partition(doc, {**catalog, 'source_sha256': 'stale'}, policy)
            policy['products'][0]['shell_rules'][0]['shell_ids'] = [999]
            with self.assertRaisesRegex(ValueError, 'source subset'):
                compile_partition(doc, self.catalog(doc), policy)


if __name__ == '__main__':
    unittest.main()
