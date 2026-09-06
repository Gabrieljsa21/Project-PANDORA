# -*- coding: utf-8 -*-
"""3ª leva da reforma de taxonomia (2026-09-02) - pedido do usuário "pode
já corrigir esses pontos" respondendo à recomendação de revisar os 87
personagens que sobraram em Bardo depois do split por franquia (Ídolo).

Cada um foi lido individualmente (descrição completa) e reclassificado
numa classe JÁ EXISTENTE que fizesse sentido de verdade:
- Bardo: só quem é músico/banda/ator/performer/cheerleader/carismático de
  verdade (definição do próprio prompt de classificação - "anima o
  grupo") sobrevive aqui.
- Ídolo: mais 7 que eram idol/grupo idol mas a série não bateu com os
  marcadores de franquia da leva anterior (descrição cita "idol"
  diretamente).
- Artífice: artistas/escritores/animadores/caligrafistas - criam, não
  performam nem lutam.
- Encantador: quem "manipula/tease" os outros (bate com a definição do
  próprio prompt pra Encantador) - não recria "Truqueiro" (já foi
  fundido em Encantador na leva anterior).
- Místico: 1 caso de delusão de poder místico (chuunibyou), mesmo
  raciocínio já usado pra Rikka Takanashi na leva anterior.
- Apoiador: fallback genérico pra quem não tem combate/poder/performance/
  arte real na descrição (colega de escola comum, personagem de apoio
  sem traço distintivo) - mesmo critério já usado nas levas anteriores.

Backup feito ANTES em `data/pandora_backup_pre_bardo_individual_2026-09-
02.db`."""
import sqlite3

CAMINHO_BANCO = "data/pandora.db"

RECLASSIFICACOES = {
    # id: (classe_final, justificativa curta)
    112: ("Artífice", "Mashiro Shiina é uma artista/pintora mundialmente famosa."),
    668: ("Místico", "Ruri Gokou (Kuroneko) tem delusões chuunibyou de grandeza, mesmo padrão de Rikka Takanashi."),
    573: ("Apoiador", "Salama é só uma colega de trabalho realista/desapegada, sem traço de combate/performance."),
    549: ("Apoiador", "Ryouko Asakura é socialmente ativa (presidente de classe) mas sem arquétipo de RPG claro."),
    704: ("Apoiador", "Emi Ibarazaki é uma atleta animada, sem combate/performance/poder descrito."),
    2379: ("Apoiador", "Maekawa é uma colega de classe sem traço distintivo além de ser desastrada com fantasias."),
    3950: ("Apoiador", "Shia Hauria não tem combate/poder/performance central, só personalidade egocêntrica."),
    4223: ("Apoiador", "Erasa é só uma colega de escola falante, sem arquétipo de RPG."),
    5068: ("Apoiador", "Akari Yamamoto é só a melhor amiga da protagonista, sem traço distintivo."),
    5963: ("Apoiador", "Kotone Kashiwagi é uma otaku tímida escondendo o hobby, sem combate/performance."),
    6368: ("Apoiador", "Kaho Hinata é garçonete tsundere, sem arquétipo de RPG."),
    6577: ("Apoiador", "Natsuki é só uma colega do clube de literatura, sem performance/combate central."),
    7679: ("Apoiador", "Megumi Kayano é só uma colega apaixonada e falante, sem arquétipo claro."),
    7724: ("Apoiador", "Mero é funcionária de um café, sem traço de combate/performance."),
    7865: ("Apoiador", "Sakura Kagamihara é personagem de apoio sem traço distintivo além de dirigir a irmã."),
    10473: ("Apoiador", "Yui Amami trabalha no café da família, sem arquétipo de RPG."),
    11880: ("Apoiador", "Mayako Yamamoto é só uma colega ativa e desastrada, sem traço central."),
    12181: ("Apoiador", "Biwa Hanamaru não tem quase nenhuma informação além de 'a décima irmã'."),
    13445: ("Apoiador", "Ame é uma IA de serviço que só quer deixar todos felizes, sem performance real."),
    16470: ("Apoiador", "Sakura Asagiri é só uma colega educada e alegre, sem arquétipo claro."),
    17465: ("Apoiador", "Nono Agata é só uma irmã mimada, sem traço distintivo."),
    17636: ("Apoiador", "Hikari Hazakura é professora de educação física, ocupação sem arquétipo de combate/performance."),
    18988: ("Apoiador", "Touka Araya é uma transferida despreocupada, sem traço central."),
    19861: ("Apoiador", "Hina Nemoto é colega de fundo sem nenhum traço descrito."),
    20972: ("Apoiador", "Ao Sorakado trabalha numa doceria e é amigável, sem arquétipo de RPG."),
    21575: ("Apoiador", "Rena Natsukawa é só uma colega/vizinha, sem traço distintivo."),
    21733: ("Apoiador", "Mikka é uma amiga de infância gentil, sem traço distintivo."),
    25702: ("Apoiador", "Maguro Sasaki é filho de peixeiro estiloso, sem arquétipo de combate/performance."),
    28752: ("Apoiador", "Miko é FÃ de uma idol, não performer ela mesma - sem arquétipo próprio."),
    616: ("Artífice", "Sawamura Eriri Spencer é ilustradora de visual novel."),
    2538: ("Artífice", "Misa Toudou trabalha em produção de animação (2D/3D)."),
    5791: ("Artífice", "Yumi Iguchi é supervisora de animação num estúdio."),
    5132: ("Artífice", "Nayuta Kani é uma romancista premiada."),
    9603: ("Artífice", "Katsushika Hokusai (Fate/GO) é o pintor histórico, definido pela arte."),
    18320: ("Artífice", "Kosaka Akane é artista e fundou um grupo de arte."),
    19186: ("Artífice", "Kosuke Kanzaki é calígrafo, definido pela arte da caligrafia."),
    22636: ("Artífice", "Sia Sayourang é escritora de webtoon."),
    2459: ("Encantador", "Charlotte Hazelrink gosta de provocar/atazanar - bate com a definição de Encantador (manipula/seduz), não com performance."),
    7740: ("Encantador", "Hayase Nagatoro provoca/atazana o senpai constantemente - mesmo arquétipo."),
    11727: ("Encantador", "Kaoru Hasebe adora provocar as pessoas."),
    13266: ("Encantador", "Chiharu Ichikura espalha fofoca e provoca o irmão gêmeo."),
    24572: ("Encantador", "Juri Enokida gosta de provocar o namorado."),
    1645: ("Ídolo", "Rockhopper Penguin é integrante do grupo idol-paródia PPP (Kemono Friends)."),
    4116: ("Ídolo", "Cocoa Amaguri é descrita como 'famous pop idol' explicitamente."),
    7081: ("Ídolo", "Saki Sukinasaki é idol, forma o grupo idol Kiyoterae."),
    11708: ("Ídolo", "Tachibana Mari é integrante do grupo idol Gokudoruzu."),
    12176: ("Ídolo", "Michiru Ogawa canta em dupla idol."),
    13427: ("Ídolo", "Tsubaki é integrante do grupo idol Horny Sentries."),
    13995: ("Ídolo", "Kaede Kurobane é descrita só como 'An idol.'"),
}


def main():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    antes = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = 'Bardo'").fetchone()["n"]
    print(f"Bardo antes: {antes}")

    contagem_destino = {}
    for personagem_id, (classe_final, justificativa) in RECLASSIFICACOES.items():
        linha = cur.execute("SELECT nome, classe FROM colecao_personagens WHERE id = ?", (personagem_id,)).fetchone()
        if linha is None:
            print(f"  #{personagem_id}: NÃO ENCONTRADO - pulei.")
            continue
        if linha["classe"] != "Bardo":
            print(f"  #{personagem_id} {linha['nome']}: já não está mais em Bardo (está em '{linha['classe']}') - pulei.")
            continue
        cur.execute(
            "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ?",
            (classe_final, classe_final, personagem_id),
        )
        contagem_destino[classe_final] = contagem_destino.get(classe_final, 0) + 1
        print(f"  #{personagem_id} {linha['nome']}: Bardo -> {classe_final} ({justificativa})")

    conn.commit()

    depois = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = 'Bardo'").fetchone()["n"]
    print(f"\nBardo depois: {depois}")
    print("Destinos:", contagem_destino)

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
    print("Classes órfãs:", [r["classe"] for r in orfas] if orfas else "nenhuma")

    conn.close()


if __name__ == "__main__":
    main()
