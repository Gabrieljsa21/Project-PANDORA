"""Regressões do painel de Fusão reaproveitado da Party."""
from pathlib import Path


PASTA_PROJETO = Path(__file__).resolve().parent.parent


def testar_fusao_reutiliza_formacao_e_nao_usa_nomes():
    painel = "\n".join(p.read_text(encoding="utf-8") for p in sorted((PASTA_PROJETO / "pandora" / "paineis").glob("*.py")))
    consulta = (PASTA_PROJETO / "pandora" / "consulta.py").read_text(encoding="utf-8")
    assert 'tipo="fusao"' in painel
    assert 'disabled=not cheio' in painel
    assert 'Preencha os 5 slots para liberar a Fusão.' in painel
    assert "resolver_nomes_unicos" not in painel
    assert "resolver_nomes_unicos" not in consulta
