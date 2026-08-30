# TODO - Project PANDORA

### Validar que "GAIA não respondeu a tempo" parou de verdade (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

Causa raiz corrigida (`asyncio.to_thread` em todo scan de coleção
inteira - ver `ARQUITETURA.md`, seção Auto-Party) e validada só em
cópia/script (resultado idêntico direto vs. via thread + prova de que o
event loop fica livre durante a chamada) - nenhuma validação ao vivo sob
uso concorrente de verdade ainda. Testar: Auto-Party, "🏙️ Cidade" e
"🔍 Personagem" repetidas vezes, IDEALMENTE com outra pessoa usando o bot
ao mesmo tempo (é exatamente esse cenário - 2 interações concorrentes -
que expunha o bug), confirmar que nenhum dos 3 cai mais em "GAIA não
respondeu a tempo". Se cair de novo, o próximo suspeito é algum OUTRO
scan de coleção inteira que ainda não foi convertido pra `to_thread`
(checar `torre.ordenar_por_power`/`power_personagem` por chamadas soltas
fora das já corrigidas).

### GAIA precisa reiniciar pra `funcao_cidade` valer em classificações NOVAS (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

O prompt de `classificar_personagem_colecao` (GAIA) já pede `funcao_
cidade` na mesma chamada de classe/categoria_combate, mas a GAIA não foi
reiniciada ainda nesta sessão - toda personagem reivindicada AGORA (antes
do reinício) fica sem `funcao_cidade`, ficando de fora da produção da
Cidade até uma reclassificação manual futura. As 39 classes já existentes
foram cobertas por backfill manual (`backfill_funcao_cidade_2026-08-30.py`)
- só personagens com classe NOVA (nunca vista) dependem do reinício.
Avisado ao usuário antes de reiniciar, não feito sem confirmação.

### Validar Progressão Global + Cidade ao vivo no Discord (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só na camada de dados/matemática numa CÓPIA do
banco de produção (curva de XP, cascata de nível, `bonus_cp_global`
batendo com os exemplos da análise, `power_personagem` com bônus,
marcos de coleção, Divórcio/Merge/Torre creditando XP, produção da
Cidade com teto de 168h) - nenhum clique real no Discord ainda. Testar:
campo "📈 Progressão" aparece certo no hub, comprar "🏋️ Treinamento
Global"/"📊 Potencial da Coleção" na Loja, abrir "🏙️ Cidade" (1ª visita
não credita nada, visita seguinte credita proporcional ao tempo), CP
mostrado em qualquer tela (Party/Torre/card) já reflete o bônus global.

**Já validado ao vivo pelo usuário no mesmo dia** (achados corrigidos):
"🎲 Rolar" do hub volta a rolar o ciclo inteiro, preço de "Garantir" bate
com metade de "Comprar", CP aparece em "📚 Minha coleção" e no card
"🔍 Personagem", Favoritar mudou pro card "🔍 Personagem" - só falta
confirmar que essas 4 correções específicas também se comportam certo
depois do próximo reinício do ERIS.

### ~~Taxas diferenciadas por Função da Cidade~~ RESOLVIDO (2026-08-30)

Virou Cidade v2 - cada área tem efeito próprio (Militar/Arcano/
Administração são bônus de CP ao vivo pra Party; Saúde/Cultura/Comércio
geram Soulstone/XP/WiShards, cada um só o seu) - ver "Cidade v2" no
`ARQUITETURA.md`. Taxas ainda são primeiro palpite (exceto `TAXA_BONUS_
COLECAO`, literal do usuário) - já recalibradas 1x depois de testar
contra uma conta real, mas continuam candidatas a ajuste fino depois de
validar ao vivo por mais tempo.

### Validar Cidade v2 + Soulstone/Afinidade + dropdown de nível ao vivo no Discord (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só na camada de dados/matemática numa CÓPIA da
produção (3 ramos do reencontro, `subir_afinidade_ate` nunca seta
Soulmate, remigração das 40 classes sem nenhuma fora da taxonomia v2,
`calcular_power_party` batendo com a fórmula esperada, dropdown de
nível/afinidade com custo total certo e rejeitando alvo inválido, select
"Trocar de personagem" listando os candidatos certos e atualizando o
card sem reconstruir a View) - nenhum clique real no Discord ainda.
Testar: botão "💕 Aumentar Afinidade" e "⬆️ Upar Nível" abrindo o
dropdown certo no card "🔍 Personagem" (opções/custos batendo, confirmar
debitando certo, Cancelar voltando pro card, placeholder mostrando o
saldo de WiShards/Soulstone certo), select "🔄 Trocar de personagem" no
mesmo card trocando pra outra personagem da busca SEM sumir (dropdown
continua ali depois de escolher, dá pra trocar de novo em seguida),
"🏋️ Treinamento Global"/"📊 Potencial da Coleção" na Loja abrindo
o mesmo tipo de dropdown (25 opções à frente, sem nível máximo, saldo de
WiShards certo no placeholder, pular vários níveis de uma vez debitando
o total certo), opções do select "🔍 Personagem"/"🔄 Trocar de
personagem"/Merge/Party Adicionar-Remover mostrando ícone+CP+Nível+
Afinidade certos (`_descricao_personagem_dropdown`, 1 função só pras 4),
setas "◀️"/"▶️" no card "🔍 Personagem" trocando de personagem sem abrir
o select e desabilitando certo nas pontas da lista, reencontro numa
personagem em Afinidade 10 virando Soulmate de verdade, reencontro numa
já-Soulmate creditando Soulstone, painel "🏙️ Cidade" mostrando o efeito
certo de cada área, CP da Party já refletindo Bônus da Coleção/Militar/
Arcano, bônus de CP por classe aparecendo na Torre/Party.

### Limpeza de nomenclatura duplicada em `colecao_classes` (achado 2026-08-30)

Ao remigrar `funcao_cidade` pra v2, apareceram 2 pares de classe
duplicada só por idioma - "Assassin"/"Assassino" e "Invoker"/"Invocador"
(claims novos criaram a variante em inglês em algum momento entre a
sessão que criou `colecao_classes` e esta). Não corrigido agora (fora do
escopo desta leva) - fica registrado como candidato a uma limpeza futura
(reatribuir as personagens da variante em inglês pra canônica em
português e apagar a entrada duplicada de `colecao_classes`, mesmo
padrão já usado pra "Summoner"->"Invocador"/"Assassin"->"Assassino" numa
correção anterior - parece que voltou a acontecer).

## Pendências da extração (2026-08-29)

### Validar ao vivo no Discord depois do cutover

**Prioridade:** Alta | **Complexidade:** Baixa

O cutover (ERIS apontando pro pacote novo, banco de produção migrado,
processo reiniciado) foi validado via script direto contra o banco e via
atividade automática do auto-colecionador (rolou/gravou no `pandora.db`
novo com sucesso) - mas nenhum fluxo que depende de CLICAR um botão no
Discord foi testado manualmente ainda depois do cutover (roll/claim via
`/waifu`, trocas, Party, Prova de Soulmate). Testar isso é o próximo passo
antes de considerar a extração 100% encerrada.

### ~~Limpar personagens com classe "Maid"/"Mediador"~~ QUASE RESOLVIDO (2026-08-30)

7 das 9 reclassificadas manualmente (bio de cada uma lida direto do
banco, `colecao_personagens.descricao` - mesmo texto que a GAIA veria):
Mei Tachibana -> Eremita (guardada/desconfiada, mas honesta - classe
NOVA, só ela usa até agora), Setsuna Kiyoura -> Curandeira (protege a
felicidade da amiga, acalma com empatia), Erasa -> Barda (carismática,
anima o grupo), Rio Nanase -> Sábia (severa, supervisiona os estudos dos
outros), Madoka Yachi -> Sábia (dura por fora, guia a filha a crescer),
Aisha Hart -> Curandeira ("muito gentil e misericordiosa"), Fiona Thyme
-> Guardiã/Tank (Huntress leal, protege seu povo em vez de buscar
glória).

**2 ficaram de propósito, bio fina demais pra decidir sem chutar**:
Ayame Satsuki (Qwaser of Stigmata, "Maid") - personagem de apoio/
fanservice, obcecada por outra personagem, sem estilo de combate nem
poder próprio descrito (o Soma dela é SUGADO por outra personagem, não
usado por ela); Hina Ebina (Oregairu, "Mediador") - descrição de só 1
frase ("garota quieta que anda com a turma de Hayama"), sem
personalidade suficiente pra traduzir com confiança. Precisa de mais
contexto (bio mais completa/conferir a obra de verdade) antes de
reclassificar essas 2 - não é um find-and-replace, cada uma precisa de
julgamento individual.

### Validar Modo Auto-coleta por usuário ao vivo (:50/:55 de verdade)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e testado só na camada de dados (toggle liga/desliga, `db.
rolls_disponiveis` respeitando ciclo intocado) - falta esperar um :50/:55
de verdade passar com o toggle ligado (`/waifu` -> Perfil -> "🤖
Auto-coleta") pra confirmar que `AutoColecionadorUsuarios` rola/coleta
igual ao das contas de bot, gastando a cota real da pessoa. Confirmar
também que NADA acontece se a pessoa já tiver rolado manualmente antes de
:50 (pedido explícito de não dar roll "de graça").

### Limpar tabelas `colecao_*` órfãs em `Project-ERIS/data/eris.db`

**Prioridade:** Baixa | **Complexidade:** Baixa

Ver "Migração de dado" em `ARQUITETURA.md` - as tabelas antigas continuam
fisicamente no banco do ERIS (nunca mais lidas/escritas) como rede de
segurança temporária. Apagar depois que este repo rodar em produção por um
tempo sem incidente.

### Validar Torre ao vivo no Discord

**Prioridade:** Alta | **Complexidade:** Baixa

Implementada e validada só na camada de dados/matemática (Power bate com
a tabela do documento original, andar/restrição seguem a fórmula, vitória
credita recompensa e avança andar - ver `ARQUITETURA.md`) - nenhum clique
real no Discord ainda (as Views novas/alteradas passaram só pela varredura
de sanidade de construção, não por um clique de verdade). Testar: upar
nível e divorciar pelo card "🔍 Personagem" (`/waifu` -> "🔍 Personagem" -
o Perfil não existe mais, tudo isso e Favoritar/Merge/Prova de Soulmate/
Auto-coleta vieram pro hub principal, 3 linhas de botão agora), montar uma
Party usando o filtro de role novo ao Adicionar, tentar o andar 1 na Torre
(`/waifu` -> "🗼 Torre"), confirmar que perder não trava nada (retry sem
cooldown), que os andares seguintes ficam mais difíceis de verdade e que
o ícone de categoria + CP/Nível aparecem certos no embed da Torre, no
texto "Sua Party" e nos SELECTs de Adicionar/Remover.

## Roadmap futuro

- **Geração de andares da Torre via IA** - Difficulty Engine determinístico
  + GAIA escolhe blocos de um catálogo FECHADO de mecânicas + Validator,
  já validada em princípio numa sessão anterior ("depende da Torre existir
  primeiro" - agora existe). A Torre de hoje é 100% determinística
  (fórmula geométrica de Power-alvo + rotação fixa de restrições) - a
  geração por IA substituiria isso por andares temáticos únicos, mas fica
  pra uma leva futura separada.
- **Cidade - IMPLEMENTADA (2026-08-30)**, ver "Progressão Global da conta
  + Cidade" em `ARQUITETURA.md` - a "Função da cidade" que este item
  cogitava (Produção/Comércio/Serviço/Cultura/Saúde/Administração/
  Militar) foi exatamente a taxonomia usada, `colecao_classes.
  funcao_cidade`, decidida pela GAIA na mesma classificação de sempre.
  Classes NÃO combatentes (Ferreiro, Mercador, etc.) ainda não existem no
  catálogo de propósito - a Cidade de hoje já dá função útil pras classes
  combatentes existentes (a maioria vira "Militar"), inventar classes
  civis novas sem personagem nenhuma pra usá-las ficaria pra uma leva
  futura separada, se fizer sentido.

### Merge não chama `revelar_classe` (achado 2026-08-30, ainda não corrigido)

`economia.py` (Merge - sacrificar 5 personagens por 1 melhor) nunca chama
`gacha.revelar_classe` na personagem resultante - se ela nunca foi
reivindicada em NENHUM servidor antes, pode sair do Merge sem classe (o
mesmo bug de origem corrigido pro claim normal/admin/auto-colecionador,
mas não pro Merge). Não corrigido ainda - fica registrado.
