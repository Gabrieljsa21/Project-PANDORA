# World Boss: Recompensas e Conquistas

> Spec completa trazida pelo usuário em 2026-09-01, junto de uma correção
> à Batalha 5x5 (aposta sempre paga ao desafiado + fórmula = preço da
> Loja × 2). Documento de referência - ver `ARQUITETURA.md` (seção "World
> Boss: Recompensas e Conquistas") pro que foi de fato implementado.

## 1. Estrutura das recompensas

Ao derrotar um World Boss, cada jogador REAL participante recebe
individualmente: ⭐ 1 personagem 5★ aleatória garantida, 💎 WiShards, 📈
XP de Progressão, 💠 Soulstones, 🎁 chance de recompensa rara. Bots
participam do combate mas NÃO recebem recompensas.

## 2. Personagem 5★ garantida

Funciona EXATAMENTE como se obtida via Roll → Claim normal - a
personagem não tem nenhuma distinção por vir do World Boss, participa
normalmente de todos os sistemas da coleção.

## 3. Personagem já possuída

Se a 5★ sorteada já pertence ao jogador, conta como nova cópia - segue
as regras normais de Afinidade/Soulmate/progressão por cópias (pode
inclusive completar o Soulmate).

## 4. Materiais básicos

WiShards/XP/Soulstones - não são o atrativo principal (a Cidade já é a
fonte contínua), o evento só concede quantidades adicionais. Valores a
calibrar considerando a produção real da Cidade.

## 5. Recompensas raras

1 rolagem INDEPENDENTE por jogador - o fato de alguém ganhar não afeta a
chance dos demais. Devem ser significativamente mais raras que as
recompensas básicas.

## 6. Pool de recompensas raras

🛡️ Proteção, ⚔️ Revanche, 🗝️ Chave da Torre, 🏗️ Upgrade de Construção,
📯 Chamado, 🎲 +1 Roll Permanente, 💎 +1 Claim Permanente - pesos
diferentes, Roll/Claim Permanente os mais raros de todos.

## 7. 🛡️ Proteção

Protege 1 personagem contra perda via aposta PvP enquanto ativa.
Consumível.

## 8. ⚔️ Revanche

Oportunidade especial de tentar recuperar uma personagem perdida no PvP -
NÃO devolve automaticamente, ainda precisa vencer a batalha de novo.
Consumível.

## 9. 🗝️ Chave da Torre

Ignora a restrição de categoria de 1 andar da Torre - não reduz o Power
necessário, não garante vitória. Consumível.

## 10. 🏗️ Upgrade de Construção

Sobe permanentemente o nível de uma construção da Cidade (Militar→
Quartel, Saúde→Hospital, Cultura→Academia, Administração→Prefeitura,
Comércio→Mercado, Arcano→Torre Arcana) - jogador escolhe onde usar,
melhora o efeito daquela área permanentemente.

## 11. 📯 Chamado

Escolhe qual World Boss aparece no próximo horário fixo do servidor - não
cria evento extra.

## 12. 🎲 Roll Permanente / 13. 💎 Claim Permanente

+1 roll/claim por ciclo, pra sempre - extremamente raros, podem ter
limite máximo obtido dessa forma.

## 14. Loja normal

As mesmas recompensas raras também aparecem na Loja (compra com
WiShards) - cria a relação sorte vs. economia. Itens mais fortes podem
ter estoque limitado/aparição rara/limite de compra/preço elevado;
Roll/Claim Permanente continuam extremamente restritos mesmo na loja.

## 15. Conquistas

NÃO concedem WiShards/XP/Soulstones/itens/personagens/bônus - existem só
pra registrar feitos importantes ("isso aconteceu nessa conta").

## 16. Exemplos de conquistas

Gerais (Primeiro Sangue/Caçador/Veterano/Lenda da Caçada, por contagem de
vitórias), por tipo de Boss (1 conquista por Boss dos 10), situações
especiais (Por um Fio <5% HP restante, Intocáveis 100% HP, Último
Segundo, Ataque Total DPS>70% CP, Fortaleza Tank dominante, Sustentação
Support dominante). Podem existir também pra Torre/PvP/Cidade/coleção/
Afinidade/Soulmate no futuro.

## 17/18. Resultado de uma vitória / Estrutura final

3 partes: RECOMPENSA GARANTIDA (5★+materiais), RECOMPENSA RARA (os 7
itens), REGISTRO (Conquistas, sem recompensa associada).

---

## Correção à Batalha 5x5 (mesma mensagem, 2026-09-01)

> "Desafios por waifus tem de pagar os WiShards para o desafiado, n
> sumir. E tem de ser o valor daquela raridade na loja x5 por5 n,
> multiplica por 2"

- A aposta agora SEMPRE vai pro defensor (desafiado), mesmo quando o
  desafiante vence - reverte o "sink" da spec original (Seção 3/17 do
  documento da Batalha), onde a aposta simplesmente desaparecia da
  economia se o desafiante vencesse.
- Fórmula da aposta: `Preço da Loja daquela raridade (db.PRECOS_LOJA) × 2`
  - substitui `raridade × db.valor_base_wishards(raridade)`, que dava só
    500 WiShards pra uma 5⭐ (baixo demais comparado ao preço de 5.000 pra
    COMPRAR uma na própria Loja).

## Decisões tomadas em cima de detalhes não especificados (2026-09-01)

- **Elegibilidade da 5★ garantida** - sorteada só entre 5★ SEM dono
  nesse servidor OU já do próprio jogador (nunca de OUTRO jogador) -
  garante que a recompensa "garantida" sempre beneficie quem ganhou.
- **Canal de entrega** - recompensa individual por DM (Seção 17 é
  claramente pessoal, "Suas recompensas"); resumo agregado no canal do
  evento.
- **Valores-base (primeiro palpite, Seção 4 pede calibração)**: 500
  WiShards, 200 XP, 20 Soulstone por vitória; chance de drop raro 15% por
  jogador; preços da Loja 3.000-60.000 WiShards conforme o item; +10% de
  Poder por nível de Construção (máximo 10 níveis); limite de 5 Roll/Claim
  Permanente (drop OU compra, contam juntos no mesmo limite).
