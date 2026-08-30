# -*- coding: utf-8 -*-
"""Webhook reverso PANDORA -> GAIA - EXTRAÍDO do Project-ERIS em 2026-08-29
(era `eris/integrations/gaia_webhook.py`, só as 2 funções do Colecionador -
`pedir_resposta_persona`/voz/música/lista de desejo ficaram no ERIS, que
continua sendo quem tem a conexão Discord de verdade). Mesma URL/porta de
sempre (`pandora.config.URL_BASE_GAIA`, aponta pro MESMO servidor HTTP da
GAIA que o ERIS já usava) - as rotas do lado da GAIA (`integrations/
iris_bridge.py::/eris/colecao_classificar`/`/eris/colecao_prova_soulmate`)
não mudaram nada, só quem CHAMA de dentro do Python mudou de módulo."""
import json
import urllib.request

from pandora.config import URL_BASE_GAIA

TIMEOUT_SEGUNDOS = 30  # generoso de propósito - a GAIA pode estar processando LLM/ferramenta


def _post(caminho, corpo, timeout=TIMEOUT_SEGUNDOS):
    try:
        dados = json.dumps(corpo).encode("utf-8")
        req = urllib.request.Request(f"{URL_BASE_GAIA}{caminho}", data=dados, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            corpo_resposta = resp.read()
            return json.loads(corpo_resposta) if corpo_resposta else {}
    except Exception as e:
        print(f" [PANDORA] GAIA não respondeu ({caminho}): {e}")
        return None


def pedir_classe_personagem(nome, descricao, serie, genero, classes_existentes):
    """Pede pra GAIA (LLM) decidir a classe E a categoria de combate (DPS/
    Tank/Support, Seção 16 do ERIS_sistema_colecao_wishards.md) de uma
    personagem que acabou de ser reivindicada pela 1ª vez em QUALQUER
    servidor (ver `pandora.gacha.ViewClaimMultiplo._revelar_classe`),
    NA MESMA chamada - `classes_existentes` é a taxonomia ABERTA toda já
    usada no catálogo (`db.classes_existentes()`), pra ela reaproveitar uma
    classe que já existe em vez de inventar uma quase-sinônima (a categoria
    de combate é taxonomia FECHADA, sempre uma das 3, validada do lado da
    GAIA). Devolve {"classe": str|None, "classe_exibicao": str|None,
    "categoria_combate": str|None, "funcao_cidade": str|None} - todos None
    se a GAIA estiver fora do ar/recusou - quem chama decide o que fazer
    nesse caso (hoje: deixa sem classificação, tenta de novo na próxima
    reivindicação de outra personagem sem classe ainda, nunca bloqueia o
    claim em si). `classe` é a forma CANÔNICA (masculina/singular, "Ladino"
    - usada em `classes_existentes()`/estatísticas, nunca fragmenta por
    gênero); `classe_exibicao` concorda com o gênero da personagem
    ("Ladina") e é só pra MOSTRAR (2026-08-29, pedido do usuário: "separaria
    nome canônico de nome exibido... o nome exibido pode concordar com o
    gênero"). `funcao_cidade` (2026-08-30, Cidade - "n iremos setar
    personagens em funcoes manualmente, sera automatico com base na
    classe/profissão") é o 2º campo derivado da classe, mesma taxonomia
    fechada de `categoria_combate`, decidida na MESMA chamada."""
    resultado = _post("/eris/colecao_classificar", {
        "nome": nome, "descricao": descricao or "", "serie": serie or "",
        "genero": genero, "classes_existentes": list(classes_existentes),
    })
    if not resultado:
        return {"classe": None, "classe_exibicao": None, "categoria_combate": None, "funcao_cidade": None}
    return {
        "classe": (resultado.get("classe") or "").strip() or None,
        "classe_exibicao": (resultado.get("classe_exibicao") or "").strip() or None,
        "categoria_combate": (resultado.get("categoria_combate") or "").strip() or None,
        "funcao_cidade": (resultado.get("funcao_cidade") or "").strip() or None,
    }


_CAMPOS_TEXTO_PROVA_SOULMATE = (
    "prova_soulmate_nome", "prova_soulmate_descricao", "prova_soulmate_situacao",
    "prova_soulmate_reacao_acerto", "prova_soulmate_reacao_erro",
    "prova_soulmate_derrota", "prova_soulmate_vitoria",
)


def pedir_prova_soulmate(nome, descricao, serie, genero):
    """Pede pra GAIA (LLM) gerar o conteúdo da Prova de Soulmate de uma
    personagem, na 1ª vez que ela chega em Afinidade 10 (ver
    `pandora.gacha.obter_textos_prova_soulmate`) - mesmo padrão de
    `pedir_classe_personagem` acima, cacheado pra sempre depois de gerado
    (`db.definir_textos_prova_soulmate`). Devolve um dict com os campos de
    `_CAMPOS_TEXTO_PROVA_SOULMATE` + `prova_soulmate_opcoes` (list de 3
    dicts `{"texto", "correta"}`, já validado do lado da GAIA - ver
    `core.agent.turno._normalizar_opcoes_prova_soulmate`) - todos None se a
    GAIA estiver fora do ar/recusou; quem chama cai pra um texto genérico
    nesse caso, a mecânica (chance/pity/bônus) nunca depende disso."""
    resultado = _post("/eris/colecao_prova_soulmate", {
        "nome": nome, "descricao": descricao or "", "serie": serie or "", "genero": genero,
    })
    if not resultado:
        return {**{campo: None for campo in _CAMPOS_TEXTO_PROVA_SOULMATE}, "prova_soulmate_opcoes": None}
    dados = {campo: (resultado.get(campo) or "").strip() or None for campo in _CAMPOS_TEXTO_PROVA_SOULMATE}
    dados["prova_soulmate_opcoes"] = resultado.get("prova_soulmate_opcoes") or None
    return dados
