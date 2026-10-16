# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Transport replacement preserves release bytes and rejects wrong source pins."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

from cad_archive import file_digest, verify_archive
import test_hierarchy_release as fixtures

spec=importlib.util.spec_from_file_location('repack_release',Path(__file__).resolve().parents[1]/'scripts/repack_hierarchy_release.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class RepackReleaseTests(unittest.TestCase):
    def test_all_six_payload_files_and_original_provenance_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=fixtures.HierarchyReleaseTests().package(root)
            original=fixtures.release.package_release(source,root/'old','fixture-stage1',{'source_sha256':'original','tool_commit':'original-commit'},archive_format='zip')
            report=module.repack(original,root/'new','fixture-stage1',file_digest(original),level=3)
            self.assertTrue(report['all_six_original_payload_files_byte_identical'])
            self.assertEqual(len(report['files_sha256']),6)
            with zipfile.ZipFile(original) as zipped:
                self.assertEqual((root/'new/release.json').read_bytes(),zipped.read('fixture-stage1/release.json'))
            verify_archive(root/'new/fixture-stage1.tar.zst',report['files_sha256'])
            for line in (root/'new/SHA256SUMS').read_text().splitlines():
                expected,name=line.split('  ');self.assertEqual(file_digest(root/'new'/name),expected)
            with self.assertRaises(FileExistsError):
                module.repack(original,root/'new','fixture-stage1',file_digest(original),level=3)
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                module.repack(original,root/'bad','fixture-stage1','0'*64,level=3)
            self.assertFalse((root/'bad').exists())


if __name__=='__main__':unittest.main()
