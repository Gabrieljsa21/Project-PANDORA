"""Regressão: Upar Construção não deve listar uma área já no teto atual."""
import ast
from pathlib import Path


PASTA_PROJETO = Path(__file__).resolve().parent.parent


def testar_fluxo_filtra_areas_no_teto():
    arvore = ast.parse("\n".join(p.read_text(encoding="utf-8") for p in sorted((PASTA_PROJETO / "pandora" / "paineis").glob("*.py"))))
    fluxo = next(
        no for no in arvore.body
        if isinstance(no, ast.FunctionDef) and no.name == "_fluxo_upar_construcao_direto"
    )
    codigo = ast.unparse(fluxo)
    assert "areas_disponiveis" in codigo
    assert "niveis.get(area, 0) < teto" in codigo
    assert "for area in areas_disponiveis" in codigo
