"""Registry/source agreement and failure-path regressions. No external services."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location("source_registry_app",Path(__file__).resolve().parents[1]/"backend"/"app.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class SourceRegistryTests(unittest.TestCase):
    def write_registry(self,directory,code="//@version=6\nindicator(\"Fixture\")\n",**overrides):
        manifest={"version":"fixture","source":"fixture.pine",
                  "source_sha256":hashlib.sha256(code.replace("\r\n","\n").encode()).hexdigest(),
                  "pine_title":"Fixture",**overrides}
        (directory/"current_strategy.json").write_text(json.dumps(manifest),encoding="utf-8")
        (directory/"fixture.pine").write_bytes(code.encode())
        return manifest
    def test_release_source_matches_registry(self):
        result=app.current_strategy_source()
        self.assertEqual(result["version"],"v6.4.1-sync")
        self.assertIn(result["pine_title"],result["code"])
        self.assertEqual(hashlib.sha256(result["code"].encode()).hexdigest(),result["source_sha256"])
        self.assertFalse(result["changes_to_live_tradingview"])
    def test_wrong_source_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            self.write_registry(directory,source_sha256="0"*64)
            with self.assertRaisesRegex(ValueError,"source_manifest_mismatch"):
                app.current_strategy_source(directory)
    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            self.write_registry(directory,source="../outside.pine")
            with self.assertRaisesRegex(ValueError,"invalid_source_manifest"):
                app.current_strategy_source(directory)
    def test_windows_line_endings_are_canonicalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            self.write_registry(directory,code="//@version=6\r\nindicator(\"Fixture\")\r\n")
            result=app.current_strategy_source(directory)
            self.assertNotIn("\r",result["code"])

if __name__=="__main__":unittest.main()
