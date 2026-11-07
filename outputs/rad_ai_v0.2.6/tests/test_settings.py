import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ayarlar


class CredentialSettingsTests(unittest.TestCase):
    def test_local_credentials_and_environment_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'runtime').mkdir()
            (root/'runtime/credentials.json').write_text(json.dumps({'api_id':123,'api_hash':'local-secret'}))
            with patch.object(ayarlar,'ROOT',root),patch.dict(os.environ,{},clear=True):
                settings=ayarlar.load()
                self.assertEqual(settings.api_id,123)
                self.assertEqual(settings.api_hash,'local-secret')
                self.assertNotIn('local-secret',repr(settings))
                with patch.dict(os.environ,{'TELEGRAM_API_ID':'456','TELEGRAM_API_HASH':'environment-secret'}):
                    self.assertEqual(ayarlar.load().api_id,456)
                    self.assertEqual(ayarlar.load().api_hash,'environment-secret')

    def test_missing_credentials_still_allows_panel_start(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(ayarlar,'ROOT',Path(folder)),patch.dict(os.environ,{},clear=True):
                self.assertEqual(ayarlar.load().api_id,0)


if __name__=='__main__':
    unittest.main()
