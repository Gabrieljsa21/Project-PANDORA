# -*- coding: utf-8 -*-
"""Importação em lote do catálogo externo "get_waifu"
(github.com/JiachenRen/get_waifu, `data/waifu_details.json`, ~31 mil
personagens) pra `colecao_personagens` (ver `eris/db.py`).

`sincronizar()` baixa a versão mais atual (via `baixar_catalogo`, Git LFS,
~94MB, streaming pra arquivo temporário) e reimporta (upsert por
`fonte_id`, nunca duplica) - usada pelo job semanal de `eris/colecao/
sincronizador.py` (2026-08-29), não precisa mais rodar na mão depois da
carga inicial. `importar()` continua existindo separada pra quem já tem o
JSON baixado localmente (ou quer rodar fora do ciclo semanal).

Uso manual (mesmo sem o job automático):
    curl -L -o waifu_details.json \\
        https://media.githubusercontent.com/media/JiachenRen/get_waifu/master/data/waifu_details.json
    python -m eris.colecao.importar_get_waifu waifu_details.json
"""
import json
import os
import sys

import requests

from pandora import db
from pandora.config import PASTA_DADOS

TAMANHO_LOTE = 2000

# 🔥 Mesmo endpoint do Git LFS citado no docstring do módulo - usado pelo
# download automático da sincronização contínua (`eris/colecao/
# sincronizador.py`, 2026-08-29), não só pela carga manual inicial.
URL_CATALOGO = "https://media.githubusercontent.com/media/JiachenRen/get_waifu/master/data/waifu_details.json"
CAMINHO_CACHE_CATALOGO = os.path.join(PASTA_DADOS, "catalogo_get_waifu.json")


def baixar_catalogo(destino=CAMINHO_CACHE_CATALOGO, url=URL_CATALOGO, timeout=120):
    """Baixa o JSON do catálogo (~94MB) em streaming pra não carregar tudo
    na memória de uma vez - salva num arquivo TEMPORÁRIO primeiro e só troca
    pelo destino final se o download inteiro funcionar (nunca deixa um
    arquivo pela metade no lugar de um bom de uma sincronização anterior)."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    temporario = destino + ".tmp"
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(temporario, "wb") as f:
            for pedaco in resp.iter_content(chunk_size=1024 * 1024):
                f.write(pedaco)
    os.replace(temporario, destino)
    return destino


def sincronizar(destino=CAMINHO_CACHE_CATALOGO, url=URL_CATALOGO):
    """Baixa a versão mais recente do catálogo e reimporta (upsert por
    `fonte_id`, nunca duplica - ver `db.importar_personagens`) - usado pelo
    job de sincronização contínua. Devolve a mesma string de resumo que
    `importar()` imprime, pra registrar em `colecao_sincronizacao`."""
    baixar_catalogo(destino, url)
    return importar(destino)


def _genero(bruto):
    return "masculino" if bruto.get("husbando") else "feminino"


def _serie(bruto):
    serie = bruto.get("series") or {}
    if serie.get("name"):
        return serie["name"]
    aparicoes = bruto.get("appearances") or []
    return aparicoes[0]["name"] if aparicoes and aparicoes[0].get("name") else None


def _tags(bruto):
    tags = bruto.get("tags") or []
    return ", ".join(t["name"] for t in tags if t.get("name")) or None


def _converter(bruto):
    return {
        "fonte_id": bruto["id"],
        "slug": bruto["slug"],
        "nome": bruto["name"],
        "nome_original": bruto.get("original_name"),
        "nome_romanizado": bruto.get("romaji_name"),
        "imagem_url": bruto.get("display_picture"),
        "descricao": bruto.get("description"),
        "serie": _serie(bruto),
        "genero": _genero(bruto),
        "nsfw": bool(bruto.get("nsfw")),
        "popularidade": bruto.get("likes") or 0,
        "tags": _tags(bruto),
    }


def importar(caminho_json, tamanho_lote=TAMANHO_LOTE):
    db.inicializar()
    with open(caminho_json, "r", encoding="utf-8") as f:
        bruto = json.load(f)

    total = len(bruto)
    for inicio in range(0, total, tamanho_lote):
        lote = bruto[inicio:inicio + tamanho_lote]
        db.importar_personagens(_converter(p) for p in lote)
        print(f"Importados {min(inicio + tamanho_lote, total)}/{total}")

    print("Recalculando raridade (percentil de popularidade)...")
    db.recalcular_raridade()

    resumo = f"Catálogo importado: {db.contar_personagens()} personagens em {db.CAMINHO_BANCO}."
    print(resumo)
    return resumo


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python -m eris.colecao.importar_get_waifu <caminho para waifu_details.json>")
        sys.exit(1)
    importar(sys.argv[1])
