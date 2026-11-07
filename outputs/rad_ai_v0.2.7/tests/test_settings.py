import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ayarlar


class SettingsTests(unittest.TestCase):
    def test_no_credentials_are_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'runtime').mkdir()
            (root/'runtime/credentials.json').write_text('not even valid json')
            with patch.object(ayarlar,'ROOT',root):
                settings=ayarlar.load()
                self.assertFalse(hasattr(settings,'api_id'))
                self.assertFalse(hasattr(settings,'api_hash'))

    def test_platform_selectors_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'settings.json').write_text(json.dumps({'selectors':{'package':'io.anonchat'},'telegram_selectors':{'package':'org.telegram.messenger'}}))
            with patch.object(ayarlar,'ROOT',root):
                settings=ayarlar.load()
                self.assertNotEqual(settings.selectors,settings.telegram_selectors)
