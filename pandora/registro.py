# -*- coding: utf-8 -*-
"""Log do PANDORA: um `logging.getLogger("pandora")` só, no lugar dos
`print` soltos. Sem configuração de quem importa, as mensagens continuam
saindo no stdout ATUAL (o ERIS troca `sys.stdout` por um redirecionador
de arquivo depois do import, por isso o handler consulta `sys.stdout` a
cada mensagem em vez de guardar a referência). Quem quiser outro destino
adiciona um handler próprio em "pandora" antes de importar o pacote.

Nível pela variável de ambiente `PANDORA_LOG_NIVEL` (padrão INFO; DEBUG
liga os rastros passo a passo de Séries Favoritas e Batalha)."""
import logging
import os
import sys


class _SaidaPadraoAtual(logging.Handler):
    def emit(self, record):
        try:
            print(self.format(record), file=sys.stdout, flush=True)
        except Exception:
            self.handleError(record)


log = logging.getLogger("pandora")
if not log.handlers:
    _handler = _SaidaPadraoAtual()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_handler)
    log.setLevel(os.environ.get("PANDORA_LOG_NIVEL", "INFO").upper())
    log.propagate = False
