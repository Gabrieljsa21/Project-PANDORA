"""Saldo e ledger: gasto nunca deixa saldo negativo, nem com cliques
simultâneos (os callbacks do Discord rodam em threads diferentes)."""
import threading

from pandora import economia

GUILD, JOGADOR, OUTRO = 1, 2, 3


def _em_paralelo(funcao, vezes):
    largada = threading.Barrier(vezes)
    resultados = []

    def rodar():
        largada.wait()
        resultados.append(funcao())

    threads = [threading.Thread(target=rodar) for _ in range(vezes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultados


def testar_debito_recusa_saldo_insuficiente_sem_gravar(banco):
    banco.creditar_wishards(GUILD, JOGADOR, 100, "teste")
    assert banco.debitar_wishards(GUILD, JOGADOR, 101, "teste") is None
    assert banco.saldo_wishards(GUILD, JOGADOR) == 100
    assert banco.debitar_wishards(GUILD, JOGADOR, 100, "teste") == 0


def testar_debitos_simultaneos_nunca_passam_do_saldo(banco):
    banco.creditar_wishards(GUILD, JOGADOR, 1000, "teste")
    resultados = _em_paralelo(lambda: banco.debitar_wishards(GUILD, JOGADOR, 300, "teste"), 10)
    assert sorted(r for r in resultados if r is not None) == [100, 400, 700]
    assert banco.saldo_wishards(GUILD, JOGADOR) == 100


def testar_creditos_simultaneos_nao_se_perdem(banco):
    _em_paralelo(lambda: banco.creditar_soulstone(GUILD, JOGADOR, 7, "teste"), 20)
    assert banco.saldo_soulstone(GUILD, JOGADOR) == 140


def testar_ledger_bate_com_saldo(banco):
    banco.creditar_wishards(GUILD, JOGADOR, 500, "teste")
    banco.debitar_wishards(GUILD, JOGADOR, 120, "teste")
    banco.debitar_wishards(GUILD, JOGADOR, 9999, "teste")  # recusado: não entra no ledger
    with banco.conexao() as conn:
        soma = conn.execute("SELECT SUM(quantidade) AS s, COUNT(*) AS n FROM colecao_wishards_ledger").fetchone()
    assert (soma["s"], soma["n"]) == (380, 2)
    assert banco.saldo_wishards(GUILD, JOGADOR) == 380


def testar_dois_cliques_no_mesmo_upgrade_cobram_uma_vez(banco):
    custo = banco.custo_total_upgrade_rolls_ate(0, 1)
    banco.creditar_wishards(GUILD, JOGADOR, custo * 2, "teste")
    resultados = _em_paralelo(lambda: banco.comprar_upgrade_rolls_ate(GUILD, JOGADOR, 1), 2)
    assert sorted(ok for ok, _mensagem in resultados) == [False, True]
    assert banco.nivel_upgrade_rolls(GUILD, JOGADOR) == 1
    assert banco.saldo_wishards(GUILD, JOGADOR) == custo


def _proposta(banco, oferece, pede):
    proposta_id = banco.criar_proposta_troca(GUILD, JOGADOR, OUTRO, [], oferece, [], pede)
    return banco.obter_proposta_troca(proposta_id)


def testar_troca_move_wishards_dos_dois_lados(banco):
    banco.creditar_wishards(GUILD, JOGADOR, 100, "teste")
    banco.creditar_wishards(GUILD, OUTRO, 50, "teste")
    assert economia._executar_troca(GUILD, _proposta(banco, 100, 50)) is True
    assert banco.saldo_wishards(GUILD, JOGADOR) == 50
    assert banco.saldo_wishards(GUILD, OUTRO) == 100


def testar_troca_sem_saldo_estorna_e_nao_troca(banco):
    banco.creditar_wishards(GUILD, JOGADOR, 100, "teste")
    assert economia._executar_troca(GUILD, _proposta(banco, 100, 50)) is False
    assert banco.saldo_wishards(GUILD, JOGADOR) == 100
    assert banco.saldo_wishards(GUILD, OUTRO) == 0
