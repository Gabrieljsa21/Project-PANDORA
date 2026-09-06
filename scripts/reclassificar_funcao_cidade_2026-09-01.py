# -*- coding: utf-8 -*-
"""Correção pontual de `funcao_cidade` (2026-09-01, pedido do usuário:
"valida classificação de classe, tem muito militar e poco saúde e
comercio"). Auditoria (`SELECT classe, categoria_combate, funcao_cidade,
COUNT(personagem)` contra a produção) achou 538 de ~1.086 personagens
classificados em "Militar" contra só 35 em "Saúde" e 71 em "Comércio" -
maioria mesmo sendo real (a maior parte das classes DO catálogo é mesmo
arquétipo de combate, "Militar" é o encaixe certo pra elas), mas 3 classes
estavam em "Militar" por serem DPS/Support de combate SEM checar se a
HABILIDADE em si (não a categoria de combate) já sugeria outra função:

- "Alquimista" (1 personagem) - poções/venenos/curas é Saúde, não Militar
  (o combate dela é incidental à profissão, não o oposto).
- "Engenheiro" (9 personagens) - construção/gadgets é Comércio (produção de
  bens), não Militar.
- "Elementalista" (26 personagens) - magia elemental é conjuração arcana
  (mesma família de Místico/Ocultista/Exorcista, já em "Arcano" desde a v2),
  não força militar bruta.

Não mexe nas outras 24 classes "Militar" (Guerreiro/Espadachim/Atirador/
etc.) - são combatentes de verdade, a taxonomia v2 já não tem uma função
"civil" própria pra elas (`ARQUITETURA.md`, "Cidade - IMPLEMENTADA": "classes
NÃO combatentes ainda não existem no catálogo de propósito... leva futura").
O desbalanço restante (poucas classes de Saúde/Comércio no catálogo como um
todo) é estrutural, não um erro de classificação - endereçado à parte via
recalibração de taxa (`pandora/cidade.py`, TAXA_SOULSTONE_POR_CP_HORA/
TAXA_WISHARDS_POR_CP_HORA).

Uso: python reclassificar_funcao_cidade_2026-09-01.py <caminho_do_banco>
"""
import sqlite3
import sys

CAMINHO_BANCO = sys.argv[1] if len(sys.argv) > 1 else r"C:\Workspace\Project-PANDORA\data\pandora.db"

RECLASSIFICACOES = {
    "Alquimista": "Saúde",
    "Engenheiro": "Comércio",
    "Elementalista": "Arcano",
}


def main():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    conn.text_factory = lambda b: b.decode("utf-8", "replace")

    for classe, funcao_nova in RECLASSIFICACOES.items():
        antes = conn.execute("SELECT funcao_cidade FROM colecao_classes WHERE classe = ?", (classe,)).fetchone()
        if antes is None:
            print(f"AVISO: classe '{classe}' não existe em colecao_classes - pulando.")
            continue
        qtd = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (classe,),
        ).fetchone()["n"]
        conn.execute("UPDATE colecao_classes SET funcao_cidade = ? WHERE classe = ?", (funcao_nova, classe))
        print(f"{classe}: {antes['funcao_cidade']} -> {funcao_nova} ({qtd} personagem(ns) afetado(s))")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
