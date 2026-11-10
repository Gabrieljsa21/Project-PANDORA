"""Inicialização do banco: WAL, migrações numeradas e cópia de segurança."""
import sqlite3


def testar_banco_abre_em_wal(banco):
    with banco.conexao() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def testar_inicializar_duas_vezes_nao_quebra(banco):
    banco.inicializar()
    assert banco.versao_schema() == max(versao for versao, _d, _f in banco._MIGRACOES)


def testar_numeros_de_migracao_sao_unicos_e_crescentes(banco):
    versoes = [versao for versao, _d, _f in banco._MIGRACOES]
    assert versoes == sorted(set(versoes))


def testar_migracao_numerada_roda_uma_vez_so(banco):
    """Regressão: a cópia Wishlist -> Favoritos rodava em todo boot e
    ressuscitava favorito removido."""
    with banco.conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_wishlist (guild_id, user_id, personagem_id, adicionado_em) VALUES ('1', '2', 3, 'x')"
        )
    banco.inicializar()
    with banco.conexao() as conn:
        assert conn.execute("SELECT COUNT(*) FROM colecao_favoritas").fetchone()[0] == 0


def testar_copia_de_seguranca_leva_os_dados(banco, tmp_path):
    banco.creditar_wishards(1, 2, 42, "teste")
    destino = banco.copia_de_seguranca(str(tmp_path / "copia.db"))
    copia = sqlite3.connect(destino)
    try:
        assert copia.execute("SELECT saldo FROM colecao_wishards_saldo").fetchone()[0] == 42
    finally:
        copia.close()
