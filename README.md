# Project PANDORA

Colecionador de Personagens (gacha estilo Mudae) - rolls, claims, Afinidade/
WiShards, loja, Merge, trocas, Party/Vitrine e a Prova de Soulmate.
EXTRAÍDO do [Project-ERIS](../Project-ERIS) em 2026-08-29, quando o
Colecionador já era a maioria do código/schema daquele repo (~2.780 linhas
em `eris/colecao/*`, 14 de 19 tabelas de `eris/db.py`).

Diferente dos outros satélites do ecossistema (MOIRAI/ECHO/HESTIA/IRIS -
processo próprio + ponte HTTP, sem UI), o PANDORA é uma **biblioteca Python
local, sem processo/porta próprios** - decisão explícita: todo clique de
roll/claim/troca cai dentro do orçamento de 3s de resposta do Discord, que
já causou 2 bugs reais de timeout no Colecionador antes da extração. Um
satélite HTTP colocaria uma chamada de rede em cima de CADA clique -
exatamente a categoria de bug que já foi corrigida duas vezes. Quem tem a
conexão Discord (hoje só o [Project-ERIS](../Project-ERIS)) importa este
pacote DIRETO via dependência de path (`uv`, `pyproject.toml` do ERIS), sem
rede envolvida.

Arquitetura completa e decisões de design em [`ARQUITETURA.md`](ARQUITETURA.md).

## A origem do nome

Pandora - a primeira mulher da mitologia grega, que abre a caixa (ou jarra,
"pithos" no original) proibida e liberta tudo que havia dentro. Referência
direta a um colecionador de personagens: cada roll é abrir a caixa de novo,
sem saber o que vai sair.

## Uso

Não é um processo standalone - é importado por quem tem a conexão Discord:

```python
from pandora import db, gacha, paineis, consulta, economia, auto_colecionador, sincronizador
```

`db.inicializar()` precisa ser chamado 1x no boot de quem importa (cria/
migra o schema em `data/pandora.db`, mesmo padrão de `eris.db.inicializar()`
de antes da extração).

### Migrar de uma instância antiga do Project-ERIS

Se você tem um `data/eris.db` de antes da extração (2026-08-29), rode:

```bash
python migrar_de_eris.py [caminho pro eris.db, opcional - default ../Project-ERIS/data/eris.db]
```

Copia as 14 tabelas `colecao_*` inteiras (`INSERT OR IGNORE`, seguro rodar
mais de uma vez) - nunca apaga nada do banco de origem, só lê.

## Dependências externas

- **GAIA** (`../Project G.A.I.A`, assistente pessoal do mesmo autor) - webhook
  reverso (`pandora/gaia_webhook.py`) pra classificar classe/categoria de
  combate de uma personagem e gerar o conteúdo da Prova de Soulmate via LLM.
  Se a GAIA não estiver rodando, o Colecionador cai pra classificação/texto
  genérico - a mecânica em si (rolls/claims/chance/pity) NUNCA depende
  dessa chamada responder.
