# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Release packaging refuses invalid coverage and verifies archived CAD bytes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('hierarchy_release',Path(__file__).resolve().parents[1]/'scripts/build_hierarchy_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class HierarchyReleaseTests(unittest.TestCase):
    def package(self,root):
        source=root/'package';source.mkdir()
        (source/'field.step').write_text('synthetic CAD bytes\n');(source/'NOTICE.md').write_text('source owner\n')
        report={'source_sha256':'original','source_geometry_preserved':True,'assembly_graph_verified':True,
                'source_world_placements_verified':True,'expected_placed_faces':12,
                'files_sha256':{name:release.digest(source/name) for name in ['field.step','NOTICE.md']}}
        (source/'hierarchy.json').write_text(json.dumps(report))
        (source/'native-validation.json').write_text(json.dumps({'single_root_assembly':True,'native_faces':12}))
        return source

    def test_archive_roundtrip_source_notice_manifest_and_external_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.package(root)
            release.validate_package(source,'original')
            archive=release.package_release(source,root/'release','fixture-stage1',{'source_sha256':'original'})
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(zipped.read('fixture-stage1/field.step'),(source/'field.step').read_bytes())
                self.assertEqual(zipped.read('fixture-stage1/NOTICE.md'),b'source owner\n')
                self.assertEqual(zipped.getinfo('fixture-stage1/field.step').date_time,(1980,1,1,0,0,0))
                self.assertIn('fixture-stage1/release.json',zipped.namelist())
            for line in (root/'release/SHA256SUMS').read_text().splitlines():
                expected,name=line.split('  ');self.assertEqual(release.digest(root/'release'/name),expected)

    def test_changed_bytes_failed_coverage_wrong_source_and_unsafe_names_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.package(root)
            with self.assertRaisesRegex(ValueError,'source SHA'):release.validate_package(source,'different')
            (source/'native-validation.json').write_text(json.dumps({'single_root_assembly':True,'native_faces':11}))
            with self.assertRaisesRegex(ValueError,'coverage'):release.validate_package(source,'original')
            (source/'native-validation.json').write_text(json.dumps({'single_root_assembly':True,'native_faces':12}))
            (source/'field.step').write_text('changed')
            with self.assertRaisesRegex(ValueError,'checksum'):release.validate_package(source,'original')
            with self.assertRaisesRegex(ValueError,'unsafe'):release.package_release(source,root/'bad','../escape',{})


if __name__=='__main__':unittest.main()
