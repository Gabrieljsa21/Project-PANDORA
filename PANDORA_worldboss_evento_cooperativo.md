# World Boss: Evento Cooperativo

> Spec completa trazida pelo usuário em 2026-09-01. Documento de
> referência, mesmo espírito de `PANDORA_batalha_5x5_aposta.md` - ver
> `ARQUITETURA.md` (seção "World Boss: Evento Cooperativo") pro que foi de
> fato implementado e as decisões tomadas em cima de perguntas
> respondidas (fuso horário, identidade dos bots, recompensa).

## 1. Conceito

O World Boss é um evento cooperativo periódico no qual todos os jogadores
do servidor formam um único time contra um Boss. Não existe limite máximo
de participantes. Cada jogador contribui com apenas 1 personagem, mas o
combate não trata essas personagens como unidades individuais - depois
das inscrições, todo o CP enviado é agregado por categoria (⚔️ DPS → Poder
ofensivo, 🛡️ Tank → Poder defensivo, ✨ Support → Poder de sustentação)
pra formar os atributos do time: HP, Dano por turno e Cura por turno,
contra o HP/Ataque por turno/Mecânica especial do Boss.

## 2. Horários

Aparece 4x/dia, sempre em horários fixos: 10:00, 14:00, 18:00, 22:00.
Cada aparição inicia um evento independente.

## 3. Período de inscrição

Janela de 10 minutos. Depois do encerramento, nenhum jogador pode entrar,
sair ou alterar sua participação.

## 4. Entrada manual

Durante os 10 minutos, o jogador participa pela mensagem do World Boss
escolhendo ⚔️ DPS / 🛡️ Tank / ✨ Support. Não precisa selecionar uma
personagem manualmente - o sistema procura automaticamente a personagem
de MAIOR CP que ele possui naquela categoria.

## 5. Seleção de múltiplas categorias

O jogador pode permitir mais de uma categoria - o sistema encontra a
personagem mais forte de cada categoria selecionada e envia a de maior CP
entre elas. Selecionar as três equivale a "participar com a personagem de
maior CP disponível na conta, independente da categoria".

## 6. Alteração durante as inscrições

Enquanto os 10 minutos ainda correm, o jogador pode trocar de escolha - a
participação anterior é substituída, sempre 1 personagem só. Depois do
encerramento, nenhuma alteração é permitida.

## 7. Snapshot da personagem

Ao confirmar, o sistema registra um snapshot (jogador, personagem,
categoria, CP) - esse CP fica CONGELADO pro evento, mesmo que a personagem
suba de CP depois (na coleção normal, ou durante o próprio World Boss). O
combate nunca consulta de novo o CP atual da personagem.

## 8. Entrada automática

Configuração "Entrada Automática no World Boss" - participa mesmo sem
estar presente, mas SÓ depois que os 10 minutos de inscrição terminam
(proposital - quem está presente tem a janela inteira pra escolher na
mão). Prioridade: entrada manual > entrada automática (se o jogador
entrar manualmente, a automática não executa).

## 9. Preferências da entrada automática

Também possui categorias permitidas configuráveis (ex.: só Tank+Support,
ou só Support) - o sistema usa a personagem de maior CP dentre as
categorias permitidas, sem precisar escolher uma personagem específica.

## 10. Ordem de entrada

```text
World Boss aparece → 10min de inscrição → entradas manuais →
inscrições encerram → entrada automática dos ausentes → entrada dos bots →
composição fechada → combate começa
```

## 11. Bots

Nunca iniciam um World Boss sozinhos - precisa de pelo menos 1 jogador
real (manual ou automático). Depois disso, os 2 bots SEMPRE entram, até o
fim (não são removidos se mais jogadores entrarem depois). Objetivo:
garantir pelo menos 1 DPS + 1 Tank + 1 Support no time; se a composição já
estiver completa, os bots ainda participam mesmo assim, usando a "melhor
contribuição disponível". Prioridade: (1) garantir a composição mínima,
(2) melhor contribuição disponível.

## 12. Composição mínima

Nenhum combate começa sem pelo menos 1 DPS + 1 Tank + 1 Support. Sem
limite máximo por categoria - a composição escolhida pelos jogadores
altera diretamente as características finais do time.

## 13. Formação do time agregado

Depois de fechadas as entradas, soma-se o CP congelado de cada categoria.
A batalha NÃO é "5 personagens vs. Boss" - é "1 TIME vs. 1 BOSS", os
personagens deixam de ser unidades individuais pra fins de combate.

## 14. Conversão do CP

```text
Σ CP DPS → multiplicador do Dano
Σ CP Tank → multiplicador do HP
Σ CP Support → multiplicador da Cura
```

Existem valores-base (Dano Base/HP Base/Cura Base) - o CP funciona como
MULTIPLICADOR desses valores, nunca 1:1 ("20.000 CP" ≠ "20.000 de dano").
A função de conversão precisa ter crescimento desacelerado - possibilidade
inicial: `Multiplicador(CP) = 1 + √(CP / referência)`. Valores-base,
referência e curva definitiva devem ser calibrados com dados reais das
contas - o princípio é fixo, os números são ajustáveis.

## 15. Atributos finais do time

```text
⚔️ Dano por turno = Dano Base × multiplicador(CP DPS)
🛡️ HP máximo      = HP Base × multiplicador(CP Tank)
✨ Cura por turno  = Cura Base × multiplicador(CP Support)
```

## 16. Boss

Cada World Boss nasce ANTES das inscrições com HP/ATK/mecânica especial já
definidos - NÃO escala depois de ver quem entrou. Se jogadores fortes
participarem, têm vantagem real; se a composição for ruim, pode perder.

## 17. Início do combate

Ao fechar as inscrições, composição/snapshots/atributos finais são
congelados - começa o combate automático.

## 18. Turnos

1 turno por minuto. Sequência por turno:

```text
1. Efeito especial do Boss, quando aplicável
2. Time causa dano
3. Boss recebe dano
4. Boss ataca
5. Time recebe dano
6. Support aplica cura
7. Estado final é calculado
8. Log é publicado
```

A ordem exata pode variar pra Bosses cuja mecânica exija isso.

## 19. Cura

Aplicada ao HP coletivo, nunca ultrapassa o HP máximo.

## 20. Logs no Discord

Cada turno gera uma atualização no chat (dano/ataque/cura/placar), pra a
batalha acontecer ao longo de vários minutos e poder ser acompanhada pelo
servidor em tempo real. Mecânicas especiais também aparecem no log.

## 21. Vitória e derrota

Vitória quando HP Boss ≤ 0; derrota quando HP Time ≤ 0. Pode existir
limite máximo de turnos pra impedir batalhas infinitas.

## 22. Tipos de World Boss

Todos usam o mesmo motor de combate - a diferença está na mecânica
especial:

1. **🐉 Dragão Ancião - Enfurecer**: ATK +10% a cada turno (favorece dano
   rápido).
2. **🩸 Rei Vampiro - Drenar Vida**: % do dano causado AO GRUPO retorna
   como HP do Boss.
3. **🪞 Doppelgänger - Adaptação**: identifica a categoria de maior CP
   agregado do time e pune ela (DPS: -25% dano do grupo; Tank: +25% ATK do
   Boss; Support: -25% cura do grupo).
4. **☠️ Senhor da Morte - Ceifar**: periodicamente (turnos 3, 6, 9...)
   causa dano = % do HP máximo do time, ignorando parte das regras
   defensivas normais.
5. **🔥 Fênix Eterna - Renascimento**: precisa ser derrotada 3x (1ª morte:
   HP 70%/ATK +20%; 2ª morte: HP 40%/ATK +40%; 3ª morte encerra de vez).
6. **🗿 Colosso de Pedra - Barreira**: barra adicional que absorve TODO
   dano enquanto existir (ATK do Boss -30% enquanto protegido, +30% depois
   de romper - muda a batalha de fase defensiva pra agressiva).
7. **🌑 Devorador do Abismo - Consumir**: reduz Dano/HP máximo/Cura do
   grupo em % a cada turno (cumulativo) - o CP snapshot nunca muda, só os
   valores derivados daquele combate.
8. **👑 Rei Demônio - Posturas**: alterna entre Guerra (dano recebido pelo
   Boss -30%), Ruína (ATK do Boss +30%) e Corrupção (cura do grupo -50%),
   numa sequência previsível.
9. **🐍 Hidra - Cabeças**: 1 barra de HP só, mas múltiplas cabeças com
   efeitos próprios (ex.: ATK+20%/Regeneração/Cura-20%) que somem conforme
   limites de HP (75%/50%/25%) são cruzados.
10. **🌌 Deus do Caos - Caos**: Boss raro cuja regra muda a cada turno - 1
    efeito sorteado (dano/cura/HP/ATK modificados, boss recupera HP, dobro
    de ataque de um dos lados) dura só aquele turno.

## 23. Variação de dificuldade

Bosses podem ter perfis numéricos bem diferentes (muito HP/pouco ATK,
pouco HP/muito ATK, equilibrado) - a mecânica especial é aplicada sobre
esse perfil, permitindo que composições diferentes sejam melhores contra
Bosses diferentes.

## 24. Balanceamento

O Boss não deve ser recalculado usando os participantes do PRÓPRIO
evento (senão o progresso do jogador perde valor - "jogador entra mais
forte → Boss fica mais forte"). Cada Boss tem dificuldade definida ANTES
da inscrição; dados históricos (desempenho anterior, CP típico, taxa de
vitória, turnos médios) servem pra calibrar os PRÓXIMOS Bosses, nunca pra
alterar retroativamente o atual.

## 25. Princípio geral

3 etapas separadas: **Preparação** (escolher categoria → personagem mais
forte elegível → snapshot do CP) → **Formação** (Σ CP por categoria →
conversão → Dano/HP/Cura) → **Combate** (time agregado vs. Boss, 1
turno/minuto + mecânica especial + logs no Discord). O jogador escolhe
COMO contribuir, mas não controla ataques individualmente - a estratégia
coletiva está em decidir quanto poder o servidor dedica a cada categoria.
Deve funcionar tanto com 1 jogador real + 2 bots quanto com dezenas/
centenas de participantes, sem mudar a estrutura fundamental do combate.

---

## Decisões tomadas em cima de perguntas respondidas pelo usuário (2026-09-01)

- **Fuso horário dos 4 horários fixos**: horário de Brasília (UTC-3,
  offset fixo - Brasil não observa mais horário de verão desde 2019).
- **Identidade dos "2 bots" (Seção 11)**: o CP deles é a MÉDIA de CP dos
  participantes HUMANOS daquele evento (calculada 1x, no fechamento das
  inscrições) - não uma personagem real de nenhuma conta de bot. Ver
  "Identidade dos bots" em `ARQUITETURA.md` pro motivo (o scheduler só
  roda na instância "completo" do ERIS, sem acesso direto à coleção da
  instância "musica").
- **Recompensa**: nenhuma implementada nesta leva (a spec não define
  valores) - só o combate em si. Fica pra um pedido futuro separado.
