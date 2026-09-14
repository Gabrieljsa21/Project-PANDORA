# -*- coding: utf-8 -*-
"""Exporta a classificação de personagens já feita via LLM (`classe`/
`classe_exibicao`, ~8,7k personagens em 2026-09-14) pra um JSON VERSIONADO
em `data/classificacao_personagens.json` - pedido do usuário depois de
descobrir que `data/pandora.db` nunca foi pro git (regra `data/*.db` do
`.gitignore`, intencional - é banco de runtime): num PC novo, ou se o disco
morrer, o catálogo bruto se reimporta sozinho do get_waifu (ver
`pandora/importar_get_waifu.py`), mas a CLASSIFICAÇÃO (trabalho de LLM,
custo real, ~8,7k chamadas) se perderia pra sempre sem isso.

`raridade` não entra no snapshot - é recalculada automaticamente a cada
reimportação (`db.recalcular_raridade`), nunca precisa de backup.

Uso (rodar da RAIZ do repo, sempre que a classificação avançar bastante -
não precisa ser toda vez, só de vez em quando):
    python -m scripts.exportar_classificacao_personagens

Companheiro: `scripts/aplicar_classificacao_personagens.py` (reaplica esse
snapshot num banco novo, depois de reimportar o catálogo bruto)."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandora import db
from pandora.config import PASTA_DADOS

DESTINO = os.path.join(PASTA_DADOS, "classificacao_personagens.json")


def main():
    classificacoes = db.exportar_classificacao_personagens()
    os.makedirs(PASTA_DADOS, exist_ok=True)
    with open(DESTINO, "w", encoding="utf-8") as f:
        json.dump(classificacoes, f, ensure_ascii=False, indent=2)
    print(f"{len(classificacoes)} personagens classificadas exportadas pra {DESTINO}.")
    print("Lembre de dar `git add` nesse arquivo e commitar - ele não é ignorado pelo .gitignore.")


if __name__ == "__main__":
    main()
