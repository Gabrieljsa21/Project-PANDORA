"""Infra dos testes: cada teste que pede `banco` ganha um SQLite novo e
vazio numa pasta temporária. O banco real (`data/pandora.db`) nunca é
aberto pelos testes."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pandora import db  # noqa: E402


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PASTA_DADOS", str(tmp_path))
    monkeypatch.setattr(db, "CAMINHO_BANCO", str(tmp_path / "pandora_teste.db"))
    db.inicializar()
    return db
