"""A Fusão não pode mais selecionar personagens por texto aproximado."""
from pathlib import Path


PASTA_PROJETO = Path(__file__).resolve().parent.parent


def testar_fluxo_por_nome_foi_removido():
    painel = (PASTA_PROJETO / "pandora" / "paineis.py").read_text(encoding="utf-8")
    consulta = (PASTA_PROJETO / "pandora" / "consulta.py").read_text(encoding="utf-8")
    assert "_ModalNomesSacrificioMerge" not in painel
    assert "resolver_nomes_unicos" not in painel
    assert "resolver_nomes_unicos" not in consulta


if __name__ == "__main__":
    testar_fluxo_por_nome_foi_removido()
    print("PASS: Fusão não usa nomes aproximados")
