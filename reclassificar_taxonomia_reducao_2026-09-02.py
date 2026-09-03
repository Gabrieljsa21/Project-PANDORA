# -*- coding: utf-8 -*-
"""2ª leva da reforma de taxonomia de classes (2026-09-02, mesma sessão de
`reclassificar_taxonomia_classes_2026-09-02.py`) - pedido do usuário
depois de colar uma análise externa (GPT) sobre a mesma auditoria:
"você já tem classes específicas demais... eu reduziria bastante" +
confirmação pra rodar o plano CORRIGIDO (3 erros da análise original
revertidos - ver CHANGELOG) incluindo a divisão do Bardo em Ídolo.

Reduz 45 classes -> 25: funde arquétipos quase-sinônimos (Espadachim+
Witcher, Lutador+Lutador de Rua+Monge, etc.), recategoriza Cavaleiro e
Kaiju pra Tank (corpo grande/blindado = Tank, mesmo critério já usado
pelo prompt de classificação da GAIA), e separa o cluster idol/VTuber/
Vocaloid/Utaite do Bardo genérico numa classe nova "Ídolo" (por
FRANQUIA, não por personagem individual - ver `IDOLO_SERIES_MARCADORES`).

Backup feito ANTES em `data/pandora_backup_pre_reducao_taxonomia_
2026-09-02.db`. Mesmo raciocínio de sempre: sem migração de bônus de CP
necessária, `bonus_cp_classe`/`info_classes_em_lote` recalculam direto da
classe atual."""
import sqlite3

CAMINHO_BANCO = "data/pandora.db"

# (classes antigas, classe final, categoria_combate final, funcao_cidade final)
MERGES = [
    (["Espadachim", "Witcher"], "Espadachim", "DPS", "Militar"),
    (["Lutador", "Lutador de Rua", "Monge"], "Lutador", "DPS", "Militar"),
    (["Atirador", "Arqueiro"], "Atirador", "DPS", "Militar"),
    (["Artilheiro", "Piloto"], "Artilheiro", "DPS", "Militar"),
    (["Assassino", "Ninja", "Ladino"], "Assassino", "DPS", "Militar"),
    (["Guerreiro", "Berserker"], "Guerreiro", "DPS", "Militar"),
    (["Guardião", "Defensor", "Tanque"], "Guardião", "Tank", "Militar"),
    (["Cavaleiro"], "Cavaleiro", "Tank", "Militar"),  # só recategoriza DPS->Tank
    (["Dragão", "Kaiju"], "Colosso", "Tank", "Militar"),
    (["Místico", "Ocultista", "Espírito", "Deus"], "Místico", "Support", "Arcano"),
    (["Demonista"], "Ocultista", "Support", "Arcano"),  # renomeia (nome fica livre acima)
    (["Sábio", "Oráculo"], "Sábio", "Support", "Administração"),
    (["Mediador", "Estrategista"], "Estrategista", "Support", "Administração"),
    (["Encantador", "Truqueiro"], "Encantador", "Support", "Comércio"),
    (["Curandeiro", "Druida"], "Curandeiro", "Support", "Saúde"),
    (["Alquimista", "Engenheiro"], "Artífice", "Support", "Comércio"),
    (["Maid", "Servente"], "Apoiador", "Support", "Comércio"),
]

# Correções pontuais dentro do Bardo (2 personagens que na verdade têm
# combate/poder real claro, achadas na triagem por palavra-chave da
# mensagem anterior - as outras 4 do lote original de 6 eram falso
# positivo: Olivia é literalmente a classe "Dançarina" (apoio/buff) do
# Fire Emblem, e Miku Maekawa/Kaoru Ryuzaki já saem do Bardo sozinhas
# pelo filtro de franquia do IDOLM@STER abaixo).
RECLASSIFICACOES_INDIVIDUAIS_BARDO = {
    196: ("Místico", "Rikka Takanashi (Chunibyo) é definida pela fantasia de ser uma usuária de magia das trevas ('Wicked Lord Shingan') - poder sobrenatural (ainda que delusório), não performance/carisma."),
    1587: ("Atirador", "Wakasagihime (Touhou) participa de combate por projéteis (danmaku) como todo personagem jogável da série - mais perto de Atirador que de entretenimento."),
}

# Personagens do Bardo cuja SÉRIE indica claramente o cluster idol/
# VTuber/Vocaloid/Utaite - vira uma classe nova ("Ídolo"), Bardo
# continua com música/banda/orquestra/circo/contação de histórias em
# contexto NÃO-idol (K-ON!, Sound! Euphonium, Kaleido Star, etc.) e o
# resto que ficou ambíguo na triagem por palavra-chave (fica como
# estava, não foi lido individualmente - fora do escopo pedido).
IDOLO_SERIES_MARCADORES = [
    "idolm@ster", "love live", "bang dream", "d4dj", "idol jihen", "pri-chan",
    "idoly pride", "kageki revue starlight", "ongaku shoujo", "hololive",
    "vocaloid", "utaite", "tsukiuta", "youtube", "niconico", "budokan",
    "solmi's channel",
]


def main():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== Fusões/recategorizações ===")
    for antigas, final, categoria, funcao in MERGES:
        total = 0
        for antiga in antigas:
            qtd = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (antiga,)).fetchone()["n"]
            total += qtd
            if antiga != final:
                cur.execute("UPDATE colecao_personagens SET classe = ? WHERE classe = ?", (final, antiga))
                cur.execute("DELETE FROM colecao_classes WHERE classe = ?", (antiga,))
        cur.execute(
            "INSERT INTO colecao_classes (classe, categoria_combate, funcao_cidade) VALUES (?, ?, ?) "
            "ON CONFLICT(classe) DO UPDATE SET categoria_combate = excluded.categoria_combate, funcao_cidade = excluded.funcao_cidade",
            (final, categoria, funcao),
        )
        print(f"  {' + '.join(antigas)} -> {final} ({categoria}/{funcao}): {total} personagem(ns)")

    print("\n=== Bardo: correções individuais ===")
    for personagem_id, (nova_classe, justificativa) in RECLASSIFICACOES_INDIVIDUAIS_BARDO.items():
        linha = cur.execute("SELECT nome FROM colecao_personagens WHERE id = ?", (personagem_id,)).fetchone()
        cur.execute("UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ?", (nova_classe, nova_classe, personagem_id))
        print(f"  #{personagem_id} {linha['nome']}: Bardo -> {nova_classe}")
        print(f"      {justificativa}")

    print("\n=== Bardo -> Ídolo (split por franquia) ===")
    candidatos = cur.execute("SELECT id, nome, serie FROM colecao_personagens WHERE classe = 'Bardo'").fetchall()
    ids_idolo = [r["id"] for r in candidatos if any(m in (r["serie"] or "").lower() for m in IDOLO_SERIES_MARCADORES)]
    cur.executemany(
        "UPDATE colecao_personagens SET classe = 'Ídolo', classe_exibicao = 'Ídolo' WHERE id = ?",
        [(i,) for i in ids_idolo],
    )
    cur.execute(
        "INSERT INTO colecao_classes (classe, categoria_combate, funcao_cidade) VALUES ('Ídolo', 'Support', 'Cultura') "
        "ON CONFLICT(classe) DO UPDATE SET categoria_combate = excluded.categoria_combate, funcao_cidade = excluded.funcao_cidade"
    )
    print(f"  {len(ids_idolo)} personagem(ns) movida(s) pra Ídolo (franquias idol/VTuber/Vocaloid/Utaite).")

    restante_bardo = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = 'Bardo'").fetchone()["n"]
    print(f"  Bardo ficou com {restante_bardo} personagem(ns) (banda/orquestra/circo/resto não revisado individualmente).")

    conn.commit()

    print("\n=== Conferência final ===")
    linhas = cur.execute("SELECT classe, categoria_combate FROM colecao_classes ORDER BY categoria_combate, classe").fetchall()
    por_cat = {}
    for l in linhas:
        por_cat.setdefault(l["categoria_combate"], []).append(l["classe"])
    total_geral = 0
    for cat, classes in sorted(por_cat.items()):
        total = sum(
            cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (c,)).fetchone()["n"]
            for c in classes
        )
        total_geral += total
        print(f"  {cat}: {len(classes)} classes, {total} personagens")
    print(f"  TOTAL: {sum(len(v) for v in por_cat.values())} classes, {total_geral} personagens")

    orfas = cur.execute("""
        SELECT DISTINCT p.classe FROM colecao_personagens p
        LEFT JOIN colecao_classes cc ON cc.classe = p.classe
        WHERE p.classe IS NOT NULL AND cc.classe IS NULL
    """).fetchall()
    if orfas:
        print(f"\n  ATENÇÃO - classes órfãs (sem linha em colecao_classes): {[r['classe'] for r in orfas]}")
    else:
        print("\n  Nenhuma classe órfã - todo personagem classificado tem uma linha correspondente em colecao_classes.")

    conn.close()


if __name__ == "__main__":
    main()
