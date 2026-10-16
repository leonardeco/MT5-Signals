import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import registry  # noqa: E402
from research.registry import RegistryError  # noqa: E402


@pytest.fixture
def reg(tmp_path):
    return tmp_path / "registro.json"


def test_register_then_evaluate_once(reg):
    registry.register("H-X", "Idea", "Algo predice algo", path=reg)
    assert registry.get("H-X", path=reg)["criterio"] == registry.DEFAULT_CRITERIO
    registry.record_result("H-X", {"t_stat": 0.3}, paso=False, path=reg)
    assert registry.get("H-X", path=reg)["estado"] == "no pasa"
    with pytest.raises(RegistryError, match="ya se evaluó"):
        registry.record_result("H-X", {"t_stat": 2.5}, paso=True, path=reg)


def test_cannot_evaluate_unregistered_or_register_twice(reg):
    with pytest.raises(RegistryError, match="no está registrada"):
        registry.record_result("nada", {}, paso=True, path=reg)
    registry.register("H-Y", "Idea", "x", path=reg)
    with pytest.raises(RegistryError, match="ya está registrada"):
        registry.register("H-Y", "Idea retocada", "x", path=reg)


def test_controls_do_not_count_and_can_repeat(reg):
    registry.register("H-1", "a", "a", path=reg)
    registry.register("C-1", "control", "medir el motor actual", tipo="control", path=reg)
    assert registry.n_trials(path=reg) == 1
    registry.record_result("C-1", {"n": 1}, paso=False, path=reg)
    registry.record_result("C-1", {"n": 2}, paso=False, path=reg)
    assert registry.get("C-1", path=reg)["resultado"] == {"n": 2}


def test_project_registry_counts_the_20_historic_variants():
    data = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))
    historic = [e for e in data["entradas"] if e["id"].startswith("V-")]
    assert len(historic) == 20 and all(e["tipo"] == "hipotesis" and e["estado"] != "registrada" for e in historic)
