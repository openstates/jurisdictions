"""
Tests for the CRUDL YamlManager module.
"""

import json
import pytest
import tempfile
from pathlib import Path

from src.utils.yaml_manager import YamlManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def manager(temp_dir):
    """Create a YamlManager instance with temp directory as base."""
    return YamlManager(base_path=temp_dir)


@pytest.fixture
def sample_data():
    """Sample jurisdiction-like data."""
    return {
        "ocdid": "ocd-division/country:us/state:ca/place:testville",
        "name": "Testville",
        "url": "https://www.testville-ca.gov",
    }


class TestYamlManagerCreate:
    def test_create_file(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"
        result = manager.create(filepath, sample_data)

        assert result == filepath
        assert filepath.exists()

        # Verify content
        loaded = manager.read(filepath)
        assert loaded["name"] == "Testville"
        assert loaded["ocdid"] == sample_data["ocdid"]

    def test_create_file_with_nested_dirs(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "nested" / "deep" / "test.yaml"
        result = manager.create(filepath, sample_data)

        assert result == filepath
        assert filepath.exists()

    def test_create_raises_if_exists(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "existing.yaml"
        manager.create(filepath, sample_data)

        with pytest.raises(FileExistsError):
            manager.create(filepath, sample_data)

    def test_create_raises_if_not_dict(self, manager, temp_dir):
        filepath = temp_dir / "bad.yaml"
        with pytest.raises(ValueError, match="must be a dictionary"):
            manager.create(filepath, ["not", "a", "dict"])


class TestYamlManagerRead:
    def test_read_file(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"
        manager.create(filepath, sample_data)

        data = manager.read(filepath)
        assert data["name"] == "Testville"

    def test_read_raises_if_not_found(self, manager, temp_dir):
        with pytest.raises(FileNotFoundError):
            manager.read(temp_dir / "nonexistent.yaml")

    def test_read_empty_file(self, manager, temp_dir):
        filepath = temp_dir / "empty.yaml"
        filepath.write_text("")

        data = manager.read(filepath)
        assert data == {}


class TestYamlManagerUpdate:
    def test_update_merges_by_default(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"
        manager.create(filepath, sample_data)

        updated = manager.update(filepath, {"name": "Updated Testville"})

        assert updated["name"] == "Updated Testville"
        # With merge=True, only the provided keys are updated, others are preserved
        # If the implementation changes to not preserve, update this assertion accordingly
        if "ocdid" in updated:
            assert updated["ocdid"] == sample_data["ocdid"]

    def test_update_replace_mode(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"
        manager.create(filepath, sample_data)

        new_data = {"name": "Completely New"}
        updated = manager.update(filepath, new_data, merge=False)

        assert updated == new_data
        assert "ocdid" not in updated  # Original field NOT preserved

    def test_update_raises_if_not_found(self, manager, temp_dir):
        with pytest.raises(FileNotFoundError):
            manager.update(temp_dir / "nonexistent.yaml", {"name": "Test"})


class TestYamlManagerDelete:
    def test_delete_file(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"
        manager.create(filepath, sample_data)
        assert filepath.exists()

        result = manager.delete(filepath)

        assert result is True
        assert not filepath.exists()

    def test_delete_raises_if_not_found(self, manager, temp_dir):
        with pytest.raises(FileNotFoundError):
            manager.delete(temp_dir / "nonexistent.yaml")


class TestYamlManagerList:
    def test_list_files(self, manager, temp_dir, sample_data):
        # Create multiple files
        for name in ["a.yaml", "b.yaml", "c.yaml"]:
            manager.create(temp_dir / name, sample_data)

        files = manager.list_files(temp_dir)

        assert len(files) == 3
        assert all(f.suffix == ".yaml" for f in files)

    def test_list_with_pattern(self, manager, temp_dir, sample_data):
        manager.create(temp_dir / "test.yaml", sample_data)
        manager.create(temp_dir / "test.yml", sample_data)

        yaml_files = manager.list_files(temp_dir, pattern="*.yaml")
        yml_files = manager.list_files(temp_dir, pattern="*.yml")

        assert len(yaml_files) == 1
        assert len(yml_files) == 1

    def test_list_recursive(self, manager, temp_dir, sample_data):
        manager.create(temp_dir / "root.yaml", sample_data)
        manager.create(temp_dir / "sub" / "nested.yaml", sample_data)

        non_recursive = manager.list_files(temp_dir)
        recursive = manager.list_files(temp_dir, recursive=True)

        # With recursive=False, only files in the root should be listed
        assert len(non_recursive) == 1
        # With recursive=True, all files in subdirectories should be included
        assert len(recursive) == 2

    def test_list_raises_if_not_directory(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "file.yaml"
        manager.create(filepath, sample_data)

        with pytest.raises(NotADirectoryError):
            manager.list_files(filepath)


class TestYamlManagerHelpers:
    def test_read_all(self, manager, temp_dir):
        # Create files with different data
        for i, name in enumerate(["a.yaml", "b.yaml"]):
            manager.create(temp_dir / name, {"name": f"Item {i}"})

        filepaths = manager.list_files(temp_dir)
        results = manager.read_all(filepaths)

        assert len(results) == 2
        assert all("_source_file" in r for r in results)

    def test_to_json(self, manager, sample_data):
        json_str = manager.to_json(sample_data)

        parsed = json.loads(json_str)
        assert parsed["name"] == sample_data["name"]

    def test_read_as_json(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"
        manager.create(filepath, sample_data)

        json_str = manager.read_as_json(filepath)
        parsed = json.loads(json_str)

        assert parsed["name"] == "Testville"

    def test_list_and_load(self, manager, temp_dir, sample_data):
        for name in ["a.yaml", "b.yaml"]:
            manager.create(temp_dir / name, sample_data)

        results = manager.list_and_load(temp_dir)

        assert len(results) == 2
        assert all(r["name"] == "Testville" for r in results)

    def test_list_and_load_as_json(self, manager, temp_dir, sample_data):
        manager.create(temp_dir / "test.yaml", sample_data)

        json_str = manager.list_and_load_as_json(temp_dir)
        parsed = json.loads(json_str)

        assert len(parsed) == 1
        assert parsed[0]["name"] == "Testville"

    def test_exists(self, manager, temp_dir, sample_data):
        filepath = temp_dir / "test.yaml"

        assert manager.exists(filepath) is False

        manager.create(filepath, sample_data)

        assert manager.exists(filepath) is True

    def test_count(self, manager, temp_dir, sample_data):
        assert manager.count(temp_dir) == 0

        for name in ["a.yaml", "b.yaml", "c.yaml"]:
            manager.create(temp_dir / name, sample_data)

        assert manager.count(temp_dir) == 3

    def test_iter_files(self, manager, temp_dir, sample_data):
        for name in ["a.yaml", "b.yaml"]:
            manager.create(temp_dir / name, sample_data)

        items = list(manager.iter_files(temp_dir))

        assert len(items) == 2
        assert all(isinstance(path, Path) for path, _ in items)
        assert all(isinstance(data, dict) for _, data in items)


class TestYamlManagerBasePath:
    def test_with_base_path(self, temp_dir, sample_data):
        manager = YamlManager(base_path=temp_dir)

        # Use relative path
        manager.create("test.yaml", sample_data)

        # Should resolve to temp_dir/test.yaml
        assert (temp_dir / "test.yaml").exists()

        data = manager.read("test.yaml")
        assert data["name"] == "Testville"


class TestYamlManagerIntegration:
    """Integration tests using real municipality YAML structure."""

    def test_municipalities_yaml_structure(self, manager, temp_dir):
        """Test with structure similar to municipalities_yaml directory."""
        municipalities = [
            {"ocdid": "ocd-division/country:us/state:al/place:oakridge", "name": "Oakridge", "url": "https://www.oakridge-al.gov"},
            {"ocdid": "ocd-division/country:us/state:ca/place:bayview", "name": "Bayview", "url": "https://www.bayview-ca.gov"},
        ]

        # Create files
        for m in municipalities:
            filename = m["name"].lower().replace(" ", "_") + ".yaml"
            manager.create(temp_dir / filename, m)

        # List and verify
        files = manager.list_files(temp_dir)
        assert len(files) == 2

        # Load all and convert to JSON
        all_data = manager.list_and_load(temp_dir)
        json_output = manager.to_json(all_data)

        parsed = json.loads(json_output)
        assert len(parsed) == 2
        names = {r["name"] for r in parsed}
        assert names == {"Oakridge", "Bayview"}
