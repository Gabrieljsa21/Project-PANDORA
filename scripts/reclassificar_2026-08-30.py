# -*- coding: utf-8 -*-
"""Reclassificação em lote (2026-08-30) - análise da conversa do usuário com
o GPT sobre erros de classificação (personalidade/função narrativa em vez
de estilo de combate/poder real), validada e ajustada (Shiro/Mii checadas
por bio, Mashiro Shiina deixada sem trocar, Raphiel usa Truqueiro em vez de
criar Trapaceiro como quase-sinônimo, 7 personagens que o GPT não cobriu
classificadas com o mesmo critério)."""
from pandora import db

# (id, classe_canonica, classe_exibicao, categoria_combate)
CORRECOES = [
    (4564, "Artilheiro", "Artilheiro", "DPS"),       # Rudol von Stroheim
    (752, "Invocador", "Invocadora", "DPS"),          # Rosa
    (2972, "Invocador", "Invocadora", "DPS"),         # Misty
    (10397, "Invocador", "Invocadora", "DPS"),        # Alumi Niumbirch (rename)
    (186, "Ladino", "Ladina", "DPS"),                 # Hitagi Senjougahara
    (221, "Ocultista", "Ocultista", "Support"),       # C.C.
    (51, "Elementalista", "Elementalista", "Support"),  # Emilia
    (748, "Guardião", "Guardiã", "Support"),          # Airi Katagiri
    (1167, "Estrategista", "Estrategista", "Support"),  # Kaguya Shinomiya
    (2703, "Estrategista", "Estrategista", "Support"),  # Kurami Zell
    (849, "Encantador", "Encantadora", "Support"),    # Cinnamon
    (4512, "Oráculo", "Oráculo", "Support"),          # Noa Takigawa
    (1850, "Oráculo", "Oráculo", "Support"),          # Yasuho Hirose
    (557, "Berserker", "Berserker", "DPS"),           # Leone
    (4218, "Arqueiro", "Arqueira", "DPS"),            # Xayah
    (54, "Espadachim", "Espadachim", "DPS"),          # Asuna Yuuki
    (117, "Lutador", "Lutadora", "DPS"),              # Kirisaki Chitoge
    (156, "Lutador", "Lutadora", "DPS"),              # Carrot
    (286, "Cavaleiro", "Cavaleira", "DPS"),           # Crusch Karsten
    (508, "Assassino", "Assassina", "DPS"),           # Akame
    (757, "Atirador", "Atiradora", "DPS"),            # Riza Hawkeye
    (985, "Espadachim", "Espadachim", "DPS"),         # Ayase Ayatsuji
    (1565, "Exorcista", "Exorcista", "DPS"),          # Rei Hino
    (4675, "Lutador", "Lutadora", "DPS"),             # Blue Mary
    (710, "Truqueiro", "Truqueira", "Support"),       # Raphiel (reaproveita Truqueiro, não cria Trapaceiro)
    (40, "Berserker", "Berserker", "DPS"),            # Rem
    (3335, "Atirador", "Atiradora", "DPS"),           # Siesta (substitui fix manual de hoje mais cedo)
    (4948, "Místico", "Mística", "Support"),          # Holy Kujo
    (921, "Monge", "Monge", "DPS"),                   # Enju Aihara (substitui fix manual de hoje mais cedo)
    (1004, "Lutador", "Lutadora", "DPS"),             # Miia
    (1204, "Lutador", "Lutadora", "DPS"),             # Kyouko Hori
    (1929, "Assassino", "Assassina", "DPS"),          # Yuki Yoshida (rename)
    (30829, "Assassino", "Assassina", "DPS"),         # Gwen (rename)
    # 🔥 4 "Mediador" + 3 "Maid" que o GPT não cobriu - mesmo critério
    # (combate real > sobrenatural > arquétipo traduzido), bios muito
    # magras, escolhas conservadoras reaproveitando classes já existentes.
    (25087, "Guardião", "Guardiã", "Support"),        # Junko Hokaze (lealdade ao grupo/líder)
    (2197, "Sábio", "Sábia", "Support"),               # Koito Yuu (livraria, reflexiva)
    (1596, "Místico", "Mística", "Support"),           # Kuronuma Sawako (confundida com fantasma/Sadako)
    (16434, "Curandeiro", "Curandeira", "Support"),    # Nagisa Kashiwagi (presidente do clube de voluntariado)
    (21630, "Guardião", "Guardiã", "Support"),         # Maya Ijuuin (amiga de infância, bio rasa)
    (75, "Guardião", "Guardiã", "Support"),            # Ram (maid - protege/serve a casa)
    (1630, "Curandeiro", "Curandeira", "Support"),     # Tohru Honda (nutre/cura emocionalmente a família Sohma)
]

# 🔥 Classes NOVAS (categoria registrada 1x, canônica pra sempre - ver
# db.definir_classe_personagem) - classes REAPROVEITADAS (Cavaleiro,
# Berserker, Encantador, Guardião, Truqueiro, Sábio, Curandeiro, Ladino)
# já têm entrada, não precisam disso.
NOVAS_CLASSES = {
    "Artilheiro": "DPS", "Invocador": "DPS", "Ocultista": "Support",
    "Elementalista": "Support", "Estrategista": "Support", "Arqueiro": "DPS",
    "Espadachim": "DPS", "Lutador": "DPS", "Atirador": "DPS",
    "Exorcista": "DPS", "Místico": "Support", "Monge": "DPS", "Assassino": "DPS",
    "Oráculo": "Support",
}


def main():
    with db.conexao() as conn:
        for classe, categoria in NOVAS_CLASSES.items():
            conn.execute(
                "INSERT INTO colecao_classes (classe, categoria_combate) VALUES (?, ?) "
                "ON CONFLICT(classe) DO NOTHING",
                (classe, categoria),
            )
        for personagem_id, classe, classe_exibicao, _categoria in CORRECOES:
            conn.execute(
                "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ?",
                (classe, classe_exibicao, personagem_id),
            )
        # 🔥 Renomeação: "Summoner"/"Assassin" não são mais usadas por
        # ninguém depois do loop acima - remove as entradas antigas de
        # `colecao_classes` (senão ficariam órfãs, "classes já usadas"
        # oferecidas de novo sem sentido).
        for classe_antiga in ("Summoner", "Assassin"):
            ainda_em_uso = conn.execute(
                "SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (classe_antiga,),
            ).fetchone()["n"]
            if ainda_em_uso == 0:
                conn.execute("DELETE FROM colecao_classes WHERE classe = ?", (classe_antiga,))

    print(f"{len(CORRECOES)} personagens reclassificadas.")
    print(f"{len(NOVAS_CLASSES)} classes novas registradas.")


if __name__ == "__main__":
    main()
