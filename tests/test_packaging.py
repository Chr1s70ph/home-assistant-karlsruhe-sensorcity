"""Tests for packaging files."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_hacs_json():
    data = json.loads((ROOT / "hacs.json").read_text())
    assert data["name"] == "Karlsruhe SensorCity"
    assert data["render_readme"] is True


def test_readme_exists():
    assert (ROOT / "README.md").read_text(encoding="utf-8").startswith("# ")


def test_info_md_exists():
    assert (ROOT / "info.md").read_text(encoding="utf-8").strip()
