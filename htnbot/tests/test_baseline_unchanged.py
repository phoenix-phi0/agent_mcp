"""Guard: planner module and its tests must stay byte-identical to the baseline.

The expected sha256 values were taken from the baseline project copy
(work/planbot1) before the htn change round, not computed from the files here.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BASELINE_SHA256 = {
    "planbot/planner.py": "8765d5d8a339743b67a4aa694965b146326b0e979e5f8f07972b1a9de3177243",
    "tests/test_planner.py": "c9e9a2c514a71e963e62c5e0aafd0f64781b3e1ce4c4a8538091b1f775a5badf",
}


def _sha256(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def test_planner_py_unchanged_from_baseline():
    assert _sha256("planbot/planner.py") == BASELINE_SHA256["planbot/planner.py"]


def test_test_planner_py_unchanged_from_baseline():
    assert _sha256("tests/test_planner.py") == BASELINE_SHA256["tests/test_planner.py"]
