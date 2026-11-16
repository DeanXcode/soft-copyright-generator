from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.softcopyright.packager import make_zip_files


class PackagerLockedZipTests(unittest.TestCase):
    def test_writes_timestamped_zip_when_target_is_locked(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "manual.txt"
            source.write_text("manual", encoding="utf-8")
            target = root / "materials.zip"
            original_replace = Path.replace
            attempts = 0

            def replace_with_first_target_locked(path, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("locked")
                return original_replace(path, destination)

            with patch.object(Path, "replace", replace_with_first_target_locked):
                result = make_zip_files([source], target)

            self.assertNotEqual(result, target)
            self.assertTrue(result.exists())
            self.assertTrue(result.name.startswith("materials-"))


if __name__ == "__main__":
    unittest.main()
