"""Regressão: Militar e Arcano usam 5% do nível por marco."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pandora import cidade, personagens_favoritas, torre


def testar_militar_usa_cinco_por_cento_do_nivel():
    # 10 trabalhadores = 2 marcos; base Militar = 10 CP; Lv10 × 5% = 0,5.
    assert cidade.bonus_area("Militar", 10, 10) == 10
    assert cidade.bonus_por_marco("Militar", 10) == 5


def testar_arcano_usa_cinco_por_cento_do_nivel():
    # 10 trabalhadores = 2 marcos; base Arcano = 0,01%; Lv10 × 5% = 0,5.
    assert cidade.bonus_area("Arcano", 10, 10) == 0.0001
    assert cidade.bonus_por_marco("Arcano", 10) == 0.00005


def testar_outras_areas_mantem_multiplicador_integral():
    assert cidade.bonus_area("Saúde", 10, 10) == 10


def testar_ordem_visual_da_cidade():
    assert cidade.FUNCOES_CIDADE == (
        "Administração", "Militar", "Arcano", "Comércio", "Saúde", "Cultura",
    )


def testar_bonus_loot_da_colecao_e_linear():
    bonus = cidade.bonus_loot_colecao(308_000_000)
    assert round(bonus * 100) == 308
    assert torre.recompensa_andar(10, bonus) == 2040
    assert round(200 * (1 + bonus)) == 816
    assert round(20 * (1 + bonus)) == 82


def testar_tabela_de_slots_favoritos():
    precos = cidade.db.PRECOS_UPGRADE_SLOT_SERIE_FAVORITA
    assert precos == cidade.db.PRECOS_UPGRADE_SLOT_PERSONAGEM_FAVORITA
    assert precos[1] == 5_000_000  # Slot 6.
    assert precos[20] == 100_000_000  # Slot 25.
    assert sum(precos.values()) == 1_050_000_000


def testar_fortalecimento_do_slot_nao_pula_degraus_por_base_alta():
    # Mesmo uma personagem de Base natural 1.000 começa no primeiro patamar
    # do slot. Os degraus iniciais não mudam seu CP, mas são obrigatórios.
    power, proximo = personagens_favoritas._estado_fortalecimento(11_266, 0)
    assert round(power) == 1000
    assert proximo == 0

    # Comprar apenas o último bit não pode pular os treze anteriores.
    power, proximo = personagens_favoritas._estado_fortalecimento(11_266, 1 << 13)
    assert round(power) == 1000
    assert proximo == 0

    # Só com todos os 14 patamares o slot fica pronto para Ascensão.
    power, proximo = personagens_favoritas._estado_fortalecimento(11_266, (1 << 14) - 1)
    assert round(power) == 1000
    assert proximo is None


def testar_curva_da_torre_valida_150k_no_andar_400():
    assert torre.power_alvo_andar(1) == 1_000
    assert torre.power_alvo_andar(200) == 56_930
    assert torre.power_alvo_andar(300) == 100_000
    assert torre.power_alvo_andar(400) == 150_000


if __name__ == "__main__":
    testar_militar_usa_cinco_por_cento_do_nivel()
    testar_arcano_usa_cinco_por_cento_do_nivel()
    testar_outras_areas_mantem_multiplicador_integral()
    testar_ordem_visual_da_cidade()
    testar_bonus_loot_da_colecao_e_linear()
    testar_tabela_de_slots_favoritos()
    testar_fortalecimento_do_slot_nao_pula_degraus_por_base_alta()
    testar_curva_da_torre_valida_150k_no_andar_400()
    print("PASS: fórmulas da Cidade, loot e tabela de slots")
