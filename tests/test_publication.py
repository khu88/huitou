"""Publication guard checks use fabricated bytes, never real credentials."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('publication', Path(__file__).resolve().parents[1] / 'scripts/audit_publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_local_runtime_and_screenshots_are_not_publishable(self):
        for name in ['.local/management/backend.py', 'research/qa/screen.png',
                     'renamed.sqlite3-wal', '.env.production', 'STATUS.md', 'dist/index.html']:
            with self.subTest(name=name):
                self.assertTrue(publication.inspect_file(name, b''))

    def test_renamed_database_key_and_private_code_are_detected(self):
        database = b'SQLite format 3' + bytes([0]) + b'fixture'
        key = ('-----BEGIN ' + 'PRIVATE KEY-----').encode()
        implementation = ('def promote_' + 'admin(name): pass').encode()
        for name, content in [('assets/file.bin', database), ('notes.txt', key),
                              ('public.py', implementation)]:
            with self.subTest(name=name):
                self.assertTrue(publication.inspect_file(name, content))

    def test_normal_source_and_example_environment_are_allowed(self):
        self.assertEqual(publication.inspect_file('server.py', b'def register(name): pass'), [])
        self.assertEqual(publication.inspect_file('.env.example', b'APP_PORT=8765'), [])
        self.assertEqual(publication.inspect_file('data/conferences.json', b'{"conferences": []}'), [])

    def test_symlinks_are_not_followed_into_private_content(self):
        self.assertTrue(publication.inspect_file('assets/link.jpg', b'', symlink=True))
