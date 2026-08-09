from pathlib import Path


def test_repo_contains_required_top_level_files() -> None:
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "README.md",
        root / "pyproject.toml",
        root / "databricks.yml",
        root / "src",
        root / "tests",
        root / "docs",
    ]
    for path in required:
        assert path.exists(), f"Missing required path: {path}"


def test_python_package_is_importable() -> None:
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    import vigie_databricks  # noqa: F401

    assert vigie_databricks.__version__ == "0.2.0"


def test_databricks_bundle_is_minimal_descriptor() -> None:
    root = Path(__file__).resolve().parents[1]
    databricks_yml = root / "databricks.yml"
    content = databricks_yml.read_text(encoding="utf-8")

    assert "bundle:" in content
    assert "name: vigie-databricks-foundation" in content
    assert "resources:" in content


def test_architecture_note_describes_slice_boundaries() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "Slice 0" in doc
    assert "Slice 1" in doc
    assert "Bronze" in doc or "Silver" in doc or "Gold" in doc
