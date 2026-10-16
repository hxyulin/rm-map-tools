# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Archive bytes, metadata normalization and trailing frame checks are verified."""
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

import zstandard as zstd
from cad_archive import create_archive, verify_archive


class CadArchiveTests(unittest.TestCase):
    def fixture(self, root):
        package = root/'source'; package.mkdir()
        (package/'field.step').write_bytes(b'synthetic CAD only\n' * 500)
        (package/'NOTICE.md').write_text('upstream owner\n')
        return package

    def test_reproducible_metadata_and_default_maximum_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); package=self.fixture(root)
            first=create_archive(package,root/'first.tar.zst')
            os.utime(package/'field.step',(123456,123456))
            (package/'field.step').chmod(0o600)
            second=create_archive(package,root/'second.tar.zst')
            self.assertEqual(first['level'],22)
            self.assertEqual(first['archive_sha256'],second['archive_sha256'])
            self.assertTrue(first['frame_checksum'])
            self.assertTrue(first['all_member_sha256_verified'])

    def test_corrupt_frame_checksum_or_expected_bytes_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); package=self.fixture(root); archive=root/'package.tar.zst'
            result=create_archive(package,archive,level=3)
            wrong=dict(result['files_sha256']);wrong['NOTICE.md']='0'*64
            with self.assertRaisesRegex(ValueError,'content mismatch'):
                verify_archive(archive,wrong)
            data=bytearray(archive.read_bytes());data[-1]^=1;archive.write_bytes(data)
            with self.assertRaises(zstd.ZstdError):
                verify_archive(archive,result['files_sha256'])

    def test_missing_checksum_bytes_and_trailing_frames_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package=self.fixture(root);archive=root/'package.tar.zst'
            result=create_archive(package,archive,level=3);data=archive.read_bytes()
            for damaged in (data[:-1],data[:-4],data+data,data+b'trailing'):
                archive.write_bytes(damaged)
                with self.assertRaises((ValueError,zstd.ZstdError,tarfile.ReadError)):
                    verify_archive(archive,result['files_sha256'])

    def test_prefix_and_extra_metadata_and_invalid_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); package=self.fixture(root); extra=root/'release.json';extra.write_text('{}')
            result=create_archive(package,root/'package.tar.zst',level=3,include=['NOTICE.md'],extra_files={'release.json':extra},prefix='release')
            self.assertEqual(set(result['files_sha256']),{'release/NOTICE.md','release/release.json'})
            with self.assertRaisesRegex(ValueError,'unsafe'):
                create_archive(package,root/'unsafe.tar.zst',prefix='../escape')
            with self.assertRaises(FileExistsError):
                create_archive(package,root/'package.tar.zst')
            with self.assertRaisesRegex(ValueError,'outside'):
                create_archive(package,package/'package.tar.zst')

    def test_source_symlinks_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); package=self.fixture(root); (package/'link').symlink_to('field.step')
            with self.assertRaisesRegex(ValueError,'regular'):
                create_archive(package,root/'package.tar.zst')
            self.assertFalse((root/'package.tar.zst').exists())

    def test_target_created_during_compression_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package=self.fixture(root);target=root/'package.tar.zst'
            def competing_writer(*args):
                target.write_bytes(b'preserve competing output')
                return 0.0
            with patch('cad_archive.verify_archive',side_effect=competing_writer), self.assertRaises(FileExistsError):
                create_archive(package,target,level=3)
            self.assertEqual(target.read_bytes(),b'preserve competing output')


if __name__ == '__main__':
    unittest.main()
