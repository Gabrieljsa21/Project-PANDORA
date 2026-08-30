# -*- coding: utf-8 -*-
"""Backfill ÚNICO de `funcao_cidade` (2026-08-30, Cidade - "n iremos setar
personagens em funcoes manualmente, sera automatico com base na classe/
profissão") - `classe` é write-once (só decidida na 1ª reivindicação de
cada personagem), então as ~37 classes já existentes no catálogo nunca
teriam `funcao_cidade` preenchida sem esse script (a GAIA só passa a
decidir a função pra classificações NOVAS a partir da mudança no prompt).

Mapeamento manual (revisado por mim, não pela GAIA - é só 1x e as classes
já são conhecidas desta sessão) - fica registrado como histórico do que
foi decidido, mesmo padrão de `reclassificar_2026-08-30.py`.

Uso: python backfill_funcao_cidade_2026-08-30.py <caminho_do_banco>
"""
import sqlite3
import sys

CAMINHO_BANCO = sys.argv[1] if len(sys.argv) > 1 else r"C:\Workspace\Project-PANDORA\data\pandora.db"

FUNCAO_POR_CLASSE = {
    # Militar - toda classe de combate direto (categoria_combate DPS/Tank
    # praticamente inteira cai aqui, mesmo espírito do critério de Tank
    # revisado nesta sessão: causar dano não desqualifica).
    "Arqueiro": "Militar", "Artilheiro": "Militar", "Assassino": "Militar",
    "Atirador": "Militar", "Berserker": "Militar", "Cavaleiro": "Militar",
    "Defensor": "Militar", "Dragão": "Militar", "Elementalista": "Militar",
    "Espadachim": "Militar", "Guardião": "Militar", "Guerreiro": "Militar",
    "Invocador": "Militar", "Invoker": "Militar", "Kaiju": "Militar",
    "Ladino": "Militar", "Lutador": "Militar", "Mago": "Militar",
    "Monge": "Militar", "Ninja": "Militar", "Piloto": "Militar",
    "Tanque": "Militar", "Witcher": "Militar",
    # Saúde
    "Curandeiro": "Saúde",
    # Cultura - arte/entretenimento/conhecimento místico
    "Bardo": "Cultura", "Místico": "Cultura", "Ocultista": "Cultura", "Oráculo": "Cultura",
    # Administração - estratégia/sabedoria prática
    "Estrategista": "Administração", "Estratégista": "Administração", "Sábio": "Administração",
    # Comércio - negociação/persuasão material
    "Encantador": "Comércio", "Truqueiro": "Comércio",
    # Serviço - apoio especializado que não é cura nem combate (default
    # também pras 2 classes inválidas ainda pendentes de limpeza e pra
    # "Criança", que não tem função de combate/civil clara)
    "Exorcista": "Serviço", "Eremita": "Serviço", "Psíquico": "Serviço",
    "Maid": "Serviço", "Mediador": "Serviço", "Criança": "Serviço",
}


def main():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    conn.text_factory = lambda b: b.decode("utf-8", "replace")

    colunas = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_classes)")}
    if "funcao_cidade" not in colunas:
        print("ERRO: coluna funcao_cidade não existe ainda - rode db.inicializar() primeiro (reinicie o ERIS).")
        return

    classes_no_banco = [r["classe"] for r in conn.execute("SELECT classe FROM colecao_classes")]
    faltando_no_mapa = [c for c in classes_no_banco if c not in FUNCAO_POR_CLASSE]
    if faltando_no_mapa:
        print(f"AVISO: classes no banco sem mapeamento no script - ficarão NULL: {faltando_no_mapa}")

    for classe, funcao in FUNCAO_POR_CLASSE.items():
        cursor = conn.execute(
            "UPDATE colecao_classes SET funcao_cidade = ? WHERE classe = ? AND funcao_cidade IS NULL",
            (funcao, classe),
        )
        if cursor.rowcount:
            print(f"{classe} -> {funcao}")
    conn.commit()

    print("\n--- verificação pós-backfill ---")
    orfaos = conn.execute("SELECT classe FROM colecao_classes WHERE funcao_cidade IS NULL").fetchall()
    print(f"classes ainda sem funcao_cidade: {[r['classe'] for r in orfaos]}")
    conn.close()


if __name__ == "__main__":
    main()
