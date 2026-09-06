# Batalha 5x5 com Aposta de Personagem

> Spec completa trazida pelo usuário em 2026-09-01, em resposta à
> pergunta "o que a aposta realmente move" (recompensa só ou
> transferência de posse?) feita antes de implementar. Documento de
> referência, mesmo espírito de `ERIS_power_afinidade_soulmate_niveis.md`
> pra Torre - ver `ARQUITETURA.md` (seção "Batalha 5x5 com Aposta de
> Personagem") pro que foi de fato implementado e as decisões tomadas em
> cima do que este documento deixa como "decisão separada".

## Objetivo

A Batalha 5x5 é um modo PvP no qual um jogador pode desafiar outro para
tentar conquistar uma personagem específica da coleção dele.

Diferentemente da Torre, o PvP não utiliza o CP como fator para
determinar o vencedor. Isso permite que jogadores em estágios muito
diferentes de progressão disputem em condições competitivas.

O combate é baseado em:

- composição da Party;
- categorias DPS, Tank e Support;
- ordem escolhida para as cinco personagens;
- leitura da composição adversária.

O desafiante escolhe qual personagem deseja conquistar e coloca WiShards
em risco. O defensor coloca a personagem reivindicada em risco.

---

## 1. Início do desafio

O jogador seleciona:

```text
Jogador alvo
↓
Personagem desejada
```

Exemplo:

```text
⚔️ Desafiar jogador
Alvo: João
Personagem desejada: Rem ★★★
```

O desafiante não depende de o proprietário voluntariamente colocar
aquela personagem como aposta. Ele pode reivindicar diretamente uma
personagem da coleção adversária, respeitando as proteções e limitações
do sistema.

---

## 2. Aposta do desafiante

O defensor não precisa apostar WiShards.

O sistema calcula automaticamente quanto o desafiante precisa colocar em
risco para poder reivindicar aquela personagem.

Fórmula:

```text
Aposta em WiShards = Raridade × Preço de Mercado
```

A raridade funciona como multiplicador:

```text
★       ×1
★★      ×2
★★★     ×3
★★★★    ×4
★★★★★  ×5
```

Exemplo:

```text
Rem ★★★
Preço de mercado: 1.200 WiShards
Aposta: 3 × 1.200
Total: 3.600 WiShards
```

Quanto mais rara e valiosa for a personagem desejada, maior será o risco
econômico assumido pelo desafiante.

---

## 3. Risco de cada lado

A batalha possui riscos diferentes para cada jogador.

### Desafiante

Arrisca os WiShards calculados pelo sistema.

Se vencer: recebe a personagem reivindicada.
Se perder: perde os WiShards apostados.

### Defensor

Arrisca a personagem reivindicada.

Se vencer: mantém a personagem + recebe os WiShards do desafiante.
Se perder: a personagem é transferida para o desafiante.

O defensor nunca precisa colocar WiShards próprios na batalha.

---

## 4. CP não determina o PvP

O CP continua sendo fundamental para: Torre; progressão individual;
progressão da coleção; cidade; bônus globais.

Porém, ele não interfere diretamente no resultado da Batalha 5x5.

Uma personagem com 20.000 CP não vence automaticamente uma personagem com
2.000 CP. Isso evita que jogadores com contas muito avançadas tenham
vitória garantida contra jogadores mais novos.

Também significa que:

```text
DPS 2.000 CP vs Support 20.000 CP → DPS vence
```

se DPS possuir vantagem de categoria sobre Support.

O PvP é uma progressão estratégica separada da progressão numérica da
Torre.

---

## 5. Categorias de combate

Toda personagem possui uma das três categorias: ⚔️ DPS, 🛡️ Tank,
✨ Support.

Elas formam um sistema circular semelhante a Jokenpô:

```text
⚔️ DPS vence ✨ Support
✨ Support vence 🛡️ Tank
🛡️ Tank vence ⚔️ DPS
```

Nenhuma categoria é inerentemente superior. Cada uma vence 1, perde para
1, empata com 1.

Portanto, contra uma escolha completamente desconhecida: 33,3% vitória,
33,3% empate, 33,3% derrota.

---

## 6. Categorias iguais

Quando duas personagens da mesma categoria se enfrentam (DPS vs DPS, Tank
vs Tank, Support vs Support), o resultado é Empate.

CP não é utilizado como desempate. Isso é necessário para preservar a
simetria matemática do sistema. Se CP decidisse categorias iguais, um
jogador com personagens muito mais desenvolvidas teria vantagem em dois
dos três possíveis confrontos, quebrando a lógica de Jokenpô.

---

## 7. Formação da Party

Cada jogador utiliza exatamente cinco personagens. O jogador escolhe
também a ordem dessas cinco personagens. A ordem é secreta. Depois de
confirmada, não pode ser alterada durante os cinco confrontos iniciais.

---

## 8. Informação revelada ao defensor

O defensor recebe uma vantagem estratégica porque não foi ele quem
escolheu qual personagem seria colocada em risco. Antes de montar sua
própria Party, ele vê a distribuição de categorias escolhida pelo
desafiante.

Exemplo:

```text
⚔️ DESAFIO RECEBIDO
Personagem em risco: Rem ★★★
Valor da aposta: 3.600 WiShards
Composição do desafiante:
⚔️ DPS: 2
🛡️ Tank: 1
✨ Support: 2
Ordem: ❓ ❓ ❓ ❓ ❓
```

O defensor não vê: quais são as cinco personagens; o CP delas; a ordem
escolhida. Ele sabe apenas quantos DPS, quantos Tanks, quantos Supports.

---

## 9. Estratégia de composição

A composição passa a ser parte fundamental da batalha. Uma composição
como "2 DPS, 2 Tank, 1 Support" é mais difícil de prever que "5 DPS".
Conhecer a composição ainda não revela a ordem.

---

## 10. Resolução da batalha

As posições são enfrentadas diretamente (posição 1 vs 1, 2 vs 2, ...
5 vs 5). Porém, os resultados são revelados um por vez - cria suspense e
funciona melhor na interface do Discord do que mostrar os cinco
resultados imediatamente.

---

## 11. Condição de vitória

A batalha é vencida pelo primeiro jogador que alcançar 3 vitórias.
Empates não concedem ponto. Assim que alguém chega a três pontos, a
batalha termina.

---

## 12. Empate após as cinco posições

Como confrontos da mesma categoria geram empate, é possível terminar as
cinco posições sem nenhum jogador alcançar três vitórias. Nesse caso, a
batalha entra em 🔥 Morte Súbita: os jogadores realizam novas escolhas
secretas entre DPS/Tank/Support. O primeiro confronto que não resultar em
empate decide a batalha. As regras exatas de seleção de personagem na
Morte Súbita podem ser refinadas separadamente.

---

## 13. Transferência da personagem

Se o desafiante vencer, a personagem reivindicada passa do Defensor para
o Desafiante. A transferência é permanente. O tratamento de nível,
Afinidade, histórico, bônus e outras propriedades da personagem deve ser
definido separadamente. A Afinidade merece atenção especial porque
representa a relação entre personagem e jogador, portanto não
necessariamente deve acompanhar a transferência.

---

## 14. Proteção de Soulmate

Personagens transformadas em Soulmate não podem ser reivindicadas. Além
do valor de progressão e vínculo, Soulmate passa a funcionar como
proteção permanente daquela personagem - aumenta estrategicamente o
valor da Soulstone.

---

## 15. Limites contra perseguição

Mesmo com CP removido do combate, um jogador não deve conseguir atacar
repetidamente o mesmo usuário até eventualmente conseguir a personagem
desejada. O sistema deve possuir cooldown e/ou limite de desafios.

Exemplo inicial: após desafiar João, 24h para desafiá-lo novamente.
Também pode existir: máximo de 3 desafios recebidos por jogador por dia.
Os valores exatos devem ser balanceados posteriormente.

---

## 16. Valor de mercado

Como o valor da aposta depende do preço de mercado (raridade × preço de
mercado), o preço utilizado não pode ser facilmente manipulável. Não deve
ser simplesmente o último preço negociado, porque jogadores poderiam
realizar negociações artificiais para alterar o preço. O preço de mercado
deve utilizar uma referência mais resistente a manipulação (mediana das
negociações recentes, período mínimo de amostragem, preço-base mínimo,
exclusão de transações suspeitas). A definição exata do cálculo do preço
de mercado fica como decisão separada.

---

## 17. Exemplo completo

Gabriel deseja uma Rem pertencente a João. Personagem Rem ★★★, preço de
mercado 1.200 WiShards, aposta necessária 3 × 1.200 = 3.600 WiShards.

Gabriel seleciona 2 DPS, 1 Tank, 2 Support e define secretamente a ordem:
1. DPS, 2. Support, 3. Tank, 4. DPS, 5. Support.

João recebe o desafio vendo só a composição (2 DPS / 1 Tank / 2 Support,
ordem oculta) e monta seus cinco personagens conhecendo apenas essa
distribuição.

```text
Rodada 1: DPS > Support - Gabriel 1 x 0 João
Rodada 2: Support = Support - Gabriel 1 x 0 João
Rodada 3: Tank > DPS - Gabriel 2 x 0 João
Rodada 4: DPS < Tank - Gabriel 2 x 1 João
Rodada 5: Support > Tank - Gabriel 3 x 1 João
```

Resultado: Gabriel venceu. Rem foi transferida para Gabriel. João não
recebeu os 3.600 WiShards. A aposta de Gabriel foi encerrada.

Caso João tivesse vencido: João defendeu Rem, Rem permanece com João,
João recebeu +3.600 WiShards.

---

## 18. Princípio do PvP

A Torre e o PvP possuem objetivos diferentes. Torre: CP representa
progressão e determina força. PvP 5x5: CP não determina o resultado -
composição + ordem determinam força.

Um jogador veterano continua tendo vantagens no restante do jogo por
possuir uma coleção maior e mais desenvolvida, mas não recebe vitória
automática no PvP por ter acumulado mais CP. A Batalha 5x5 deve funcionar
como um jogo de previsão: ambos sabem quais categorias existem e o
defensor conhece a composição geral do desafiante, mas ninguém conhece a
ordem adversária. O objetivo é permitir transferência real de
personagens entre jogadores sem transformar o sistema em uma disputa
vencida automaticamente pela conta com maior tempo de jogo.
