# -*- coding: utf-8 -*-
"""Remigração ÚNICA de `funcao_cidade` pra taxonomia v2 (2026-08-30,
Cidade - efeitos diferenciados por área) - a v1 tinha 7 funções
("Produção"/"Comércio"/"Serviço"/"Cultura"/"Saúde"/"Administração"/
"Militar"); a v2 tem 6 ("Militar"/"Saúde"/"Cultura"/"Administração"/
"Comércio"/"Arcano" - "Produção"/"Serviço" SAÍRAM, "Arcano" ENTROU,
absorvendo o que era místico/oculto de Cultura e de Serviço).

Mapeamento manual (revisado por mim, mesmo critério do backfill v1) -
cobre as 40 classes que já existiam no catálogo na hora desta remigração
(inclusive achados de nomenclatura duplicada tipo "Assassin"/"Invoker" em
inglês ao lado de "Assassino"/"Invocador" - fica registrado como
candidato a limpeza de consistência numa leva futura, não é o escopo
desta remigração).

Uso: python remigrar_funcao_cidade_2026-08-30.py <caminho_do_banco>
"""
import sqlite3
import sys

CAMINHO_BANCO = sys.argv[1] if len(sys.argv) > 1 else r"C:\Workspace\Project-PANDORA\data\pandora.db"

FUNCAO_POR_CLASSE_V2 = {
    # Militar - sem mudança de conteúdo, só o nome da função (era "Militar" já)
    "Arqueiro": "Militar", "Artilheiro": "Militar", "Assassin": "Militar", "Assassino": "Militar",
    "Atirador": "Militar", "Berserker": "Militar", "Cavaleiro": "Militar", "Defensor": "Militar",
    "Dragão": "Militar", "Elementalista": "Militar", "Espadachim": "Militar", "Guardião": "Militar",
    "Guerreiro": "Militar", "Invocador": "Militar", "Invoker": "Militar", "Kaiju": "Militar",
    "Ladino": "Militar", "Lutador": "Militar", "Mago": "Militar", "Monge": "Militar",
    "Ninja": "Militar", "Piloto": "Militar", "Tanque": "Militar", "Witcher": "Militar",
    # Saúde - sem mudança
    "Curandeiro": "Saúde",
    # Cultura ENCOLHE pra só arte/entretenimento puro (Bardo)
    "Bardo": "Cultura",
    # Administração - ganha Eremita/Criança como catch-all (nenhuma das 6
    # é encaixe natural, mas função tem que ser fechada)
    "Estrategista": "Administração", "Estratégista": "Administração", "Sábio": "Administração",
    "Eremita": "Administração", "Criança": "Administração",
    # Comércio - sem mudança
    "Encantador": "Comércio", "Truqueiro": "Comércio",
    # Arcano (NOVA) - absorve o que era místico/oculto em Cultura
    # (Místico/Ocultista/Oráculo) + o que era místico em Serviço
    # (Exorcista/Psíquico) + as 2 classes inválidas pendentes de limpeza
    # (Maid/Mediador - sem efeito real, só não podem ficar sem função)
    "Místico": "Arcano", "Ocultista": "Arcano", "Oráculo": "Arcano",
    "Exorcista": "Arcano", "Psíquico": "Arcano", "Maid": "Arcano", "Mediador": "Arcano",
}


def main():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    conn.text_factory = lambda b: b.decode("utf-8", "replace")

    colunas = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_classes)")}
    if "funcao_cidade" not in colunas:
        print("ERRO: coluna funcao_cidade não existe - rode db.inicializar() primeiro.")
        return

    classes_no_banco = [r["classe"] for r in conn.execute("SELECT classe FROM colecao_classes")]
    faltando_no_mapa = [c for c in classes_no_banco if c not in FUNCAO_POR_CLASSE_V2]
    if faltando_no_mapa:
        print(f"AVISO: classes no banco sem mapeamento v2 no script - ficarão com a função v1 antiga: {faltando_no_mapa}")

    for classe, funcao in FUNCAO_POR_CLASSE_V2.items():
        cursor = conn.execute(
            "UPDATE colecao_classes SET funcao_cidade = ? WHERE classe = ? AND funcao_cidade IS NOT ?",
            (funcao, classe, funcao),
        )
        if cursor.rowcount:
            print(f"{classe} -> {funcao}")
    conn.commit()

    print("\n--- verificação pós-remigração ---")
    funcoes_v2 = set(FUNCAO_POR_CLASSE_V2.values())
    fora_da_v2 = conn.execute(
        f"SELECT classe, funcao_cidade FROM colecao_classes WHERE funcao_cidade NOT IN ({','.join('?' for _ in funcoes_v2)})",
        tuple(funcoes_v2),
    ).fetchall()
    print(f"classes com função FORA da taxonomia v2 (deveria ser vazio): {[(r['classe'], r['funcao_cidade']) for r in fora_da_v2]}")
    conn.close()


if __name__ == "__main__":
    main()
