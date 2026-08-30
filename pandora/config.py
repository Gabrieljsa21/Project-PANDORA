# -*- coding: utf-8 -*-
"""Constantes compartilhadas do PANDORA - extraído do Project-ERIS em
2026-08-29 (Colecionador de Personagens, gacha estilo Mudae). Diferente dos
outros satélites do ecossistema (MOIRAI/ECHO/HESTIA/IRIS - processo próprio +
ponte HTTP), o PANDORA é uma BIBLIOTECA PYTHON pura, sem processo nem porta
próprios - decisão explícita (2026-08-29): todo clique de roll/claim/troca
cai dentro do orçamento de 3s de resposta do Discord, e um satélite HTTP
colocaria uma chamada de rede em cima de CADA clique - risco real de
regredir os 2 bugs de timeout já corrigidos no Colecionador antes da
extração. Quem tem a conexão Discord (hoje só o Project-ERIS) importa este
pacote DIRETO (`from pandora import gacha, paineis, ...`), zero rede."""
import os

PASTA_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_DADOS = os.path.join(PASTA_PROJETO, "data")
CAMINHO_BANCO = os.path.join(PASTA_DADOS, "pandora.db")

# 🔥 Base do webhook reverso (PANDORA -> GAIA) - mesma URL que o ERIS já usa
# (`eris/config.py::URL_BASE_GAIA`) - o Colecionador pede pra GAIA classificar
# personagem/gerar a Prova de Soulmate por HTTP, igual antes da extração; só
# quem CHAMA de dentro do Python mudou de módulo (`eris.integrations.
# gaia_webhook` -> `pandora.gaia_webhook`), a rota do lado da GAIA
# (`integrations/iris_bridge.py`) não mudou nada.
URL_BASE_GAIA = os.environ.get("GAIA_WEBHOOK_URL", "http://127.0.0.1:8766")
