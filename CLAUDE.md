# Project PANDORA

Colecionador de Personagens (gacha estilo Mudae) - rolls, claims, Afinidade/
WiShards, loja, Merge, Fusão, Party, Batalha 5x5, World Boss, Torre/Cidade e
a Prova de Soulmate. Extraído do [Project-ERIS](../Project-ERIS) em
2026-08-29 - biblioteca Python local, sem processo/porta própria (import
direto, ver motivo em `README.md`), diferente dos outros satélites do
ecossistema GAIA.

Arquitetura completa, decisões de design e estado atual: ver
`docs/ARQUITETURA.md` (sempre a fonte da verdade - este arquivo não repete
detalhe técnico).

## Estrutura de pastas (reorganizado 2026-09-06, raiz estava poluída)

- **Raiz:** só o essencial de sempre - `CLAUDE.md`, `README.md`,
  `CHANGELOG.md`, `pyproject.toml`, `.gitignore`, o pacote `pandora/` e a
  pasta `data/` (runtime, banco real + backups, nunca lixo de código).
- **`docs/`** - toda documentação que não seja `README.md`/`CHANGELOG.md`:
  `ARQUITETURA.md`, `TODO.md`, `FUNCIONALIDADES.md`, e `docs/specs/` (os 3
  specs congelados, ver abaixo). Mesma convenção do `assistant/docs/` da
  GAIA.
- **`scripts/`** - scripts Python de uso único (backfill/reclassificação/
  migração), cada um já rodado e documentado no `CHANGELOG.md` na época.
  SEMPRE invocar da RAIZ do repo (`python scripts/nome.py`, nunca `cd
  scripts` primeiro) - alguns resolvem `data/pandora.db` como caminho
  relativo ao diretório de trabalho, não ao próprio arquivo. `scripts/logs/`
  guarda a saída de execuções passadas (valor de auditoria, não são
  regeráveis).

## Documentação - atualizar na hora, nunca acumular

Toda mudança de comportamento (bug corrigido, feature nova, decisão de
design) atualiza a documentação correspondente NO MESMO commit/PR - nunca
fica pra depois, nunca vira um "ritual de fechamento" separado:

- **`docs/ARQUITETURA.md`** - qualquer decisão técnica nova, ou correção de
  algo que o documento descrevia errado/desatualizado. Cada leva de mudança
  vira uma seção nova (título curto + data), inserida antes de "##
  Pendências" no fim do arquivo - nunca reescreve seções antigas pra
  "encaixar" a nova.
- **`docs/FUNCIONALIDADES.md`** - qualquer botão/comando/mecânica NOVO, ou
  que mudou de comportamento visível pro jogador (custo, requisito, texto,
  MECANISMO da interação - dropdown vs. modal vs. clique direto, quantas
  opções cabem, se dá pra escolher várias de uma vez). Documenta o ESTADO
  ATUAL do jogo (não histórico, ver `CHANGELOG.md`) - atualiza a seção
  existente direto, nunca acumula um "adendo" separado. **Sempre verificar
  contra o código de verdade** (a função Python/classe da View, não só o
  rótulo do botão) antes de escrever - já aconteceu de descrever um botão
  de forma genérica demais e deixar de fora detalhe real da interação
  (paginação de 25 em 25 por limite do Discord, ordenação por CP antes de
  cortar a lista, 2 passos onde parecia 1 só).
- **`CHANGELOG.md`** (raiz) - resumo de alto nível sob `[Unreleased]`,
  separado em blocos `### Corrigido (data, tema)`/`### Alterado (data,
  tema)`/`### Adicionado (data, tema)` por leva de mudança relacionada (não
  por commit individual) - cita a frase exata do usuário entre aspas quando
  o pedido partiu dele.
- **`README.md`** (raiz) - se mudar como importar/usar o pacote, ou a lista
  de mecânicas do parágrafo de abertura.
- **`docs/TODO.md`** - remover item quando implementado (nunca só marcar);
  item novo precisa vir com **Prioridade**/**Complexidade** preenchidos
  (mesmo padrão usado no `assistant/` da GAIA).

**Documentos de referência (histórico, NÃO atualizar):** os specs colados
pelo usuário antes de implementar uma feature grande
(`docs/specs/PANDORA_batalha_5x5_aposta.md`, `docs/specs/PANDORA_worldboss_
evento_cooperativo.md`, `docs/specs/PANDORA_worldboss_recompensas_
conquistas.md`) ficam CONGELADOS como registro do pedido original - o que
foi de fato implementado (incluindo decisões tomadas em cima de perguntas
respondidas depois) mora em `docs/ARQUITETURA.md`, nunca retroalimenta o
spec original.

## Padrões técnicos do projeto

- **Sem HTTP entre módulos** - é tudo import direto (`from pandora import
  gacha, paineis, ...`), decisão explícita pra nunca colocar rede em cima de
  um clique de Discord (orçamento de 3s de resposta). Nunca introduzir um
  padrão de satélite HTTP aqui só por "consistência" com MOIRAI/ECHO/etc.
- **`defer()` sempre a 1ª linha de qualquer callback que faça trabalho
  bloqueante** (`asyncio.to_thread`, chamada de rede) - classe de bug já
  corrigida dezenas de vezes neste projeto ("GAIA não respondeu a tempo").
- **Nunca migração destrutiva** - schema novo é sempre `ALTER TABLE`
  aditivo com `DEFAULT`, nunca recriar/truncar tabela existente.
- **Números sempre via `db.fmt_numero`** (nunca interpolar um `int`/`float`
  cru numa mensagem) - várias rodadas de correção já feitas por esquecer
  isso num embed novo.
