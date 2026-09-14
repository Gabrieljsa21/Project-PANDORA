# -*- coding: utf-8 -*-
"""2ª leva de reclassificação da taxonomia via revisão manual do usuário
com GPT externo (2026-09-06, mesma sessão do lote 1 de Apoiador) - dessa
vez mexendo em classes JÁ ESTABELECIDAS, não só em Apoiador.

Mudança MAIOR: Guerreiro (195)/Dragão (17)/Lutador (356) viram Tank (eram
DPS) - Berserker (5) funde em Guerreiro, Escalador (1) funde em Atleta -
Tank sai de 321 (5,7% do catálogo) pra 895 (15,9%), quase 3x maior.
Confirmado com o usuário (AskUserQuestion) sabendo do trade-off: isso
esvazia a razão de existir do marco=2 especial que Tank ganhou mais cedo
hoje (`db.MARCO_POR_CATEGORIA`, criado só porque Tank era raro) - usuário
escolheu reverter Tank pro marco=5 padrão junto com esta leva.

Resto são consolidações de classes quase-sinônimas com população pequena
fundidas nas maiores/mais estabelecidas (Protetor->Guardião, Arcano/
Eremita->Místico, Oráculo->Psíquico, Professor->Sábio, Controlador/
Mercador->Estrategista, Cultura->Bardo) + Exorcista virando Support
(era DPS) fundido em Ocultista.

Faz backup do banco ANTES (mesmo padrão dos scripts de reclassificação
anteriores)."""
import shutil
import sys

from pandora import db

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_taxonomia_gpt_lote2_2026-09-06.db")

# Recategorizações puras (a classe continua existindo, só muda categoria_combate)
RECATEGORIZACOES = [
    ("Guerreiro", "Tank", "Militar"),
    ("Dragão", "Tank", "Militar"),
    ("Lutador", "Tank", "Militar"),
]

# Fusões (classe de origem desaparece, personagens viram a classe destino)
FUSOES = [
    ("Berserker", "Guerreiro"),
    ("Escalador", "Atleta"),
    ("Protetor", "Guardião"),
    ("Arcano", "Místico"),
    ("Eremita", "Místico"),
    ("Oráculo", "Psíquico"),
    ("Professor", "Sábio"),
    ("Controlador", "Estrategista"),
    ("Cultura", "Bardo"),
    ("Mercador", "Estrategista"),
    ("Exorcista", "Ocultista"),  # Ocultista já é Support/Arcano - Exorcista era DPS/Arcano, vira Support ao fundir
]


def main():
    shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
    print(f"Backup salvo em {BACKUP_PATH}")

    with db.conexao() as conn:
        print("\n=== Recategorizações ===")
        for classe, categoria, funcao in RECATEGORIZACOES:
            qtd = conn.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (classe,)).fetchone()["n"]
            conn.execute(
                "UPDATE colecao_classes SET categoria_combate = ?, funcao_cidade = ? WHERE classe = ?",
                (categoria, funcao, classe),
            )
            print(f"  {classe} -> {categoria}/{funcao} ({qtd} personagem(ns))")

        print("\n=== Fusões ===")
        for origem, destino in FUSOES:
            qtd = conn.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (origem,)).fetchone()["n"]
            if qtd == 0:
                print(f"  {origem} -> {destino}: nenhum personagem, pulando.")
                continue
            conn.execute("UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE classe = ?", (destino, destino, origem))
            conn.execute("DELETE FROM colecao_classes WHERE classe = ?", (origem,))
            print(f"  {origem} ({qtd} personagem(ns)) -> {destino}")

        conn.commit()

    print("\nOK.")


if __name__ == "__main__":
    main()
