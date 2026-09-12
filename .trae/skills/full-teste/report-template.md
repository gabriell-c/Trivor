# Template do Relatório — /full-teste

Preencha **só com dados medidos**. Tempo chutado = relatório inválido.  
A esteira só fecha se **nenhum** tipo aplicável ficar `TODO`. Tipo aplicável em `GAP` → veredito no máximo **AMARELO — PARCIAL**.

---

## Relatório de Testes — [Projeto/Escopo]

**Data:** [YYYY-MM-DD]  
**Escopo:** [rota/módulo/projeto]  
**Perfil do projeto:** [ex.: API FastAPI sem frontend | full-stack | lib pura]  
**Stack:** [ex.: Python/FastAPI (+ Next.js)]  
**Orçamento de tempo:** [~15min default | sem teto | Xmin pedido]  
**Tempo total wall-clock (medido):** [Xm XXs]  
**Como mediu:** [duração do runner / Stopwatch]

---

### 1. Ledger da esteira (obrigatório — nenhum TODO)

Todo tipo do catálogo com seu estado. `N/A` precisa de motivo; `GAP` precisa de motivo.

| Tipo | Aplicável? | Estado | Evidência / motivo |
|------|-----------|--------|--------------------|
| Lint + types | sim | OK / FALHOU | `ruff check` → 0, 213ms |
| Unit | sim/N/A | OK / … | |
| Integração | sim/N/A | | |
| E2E HTTP | sim/N/A | | |
| E2E browser | sim/N/A | | **N/A: projeto sem frontend** |
| Smoke | sim | | |
| Regressão | sim/N/A | | |
| Property | sim/N/A | | |
| Fuzz | sim/N/A | | |
| Concorrência/race | sim/N/A | | N/A: stateless |
| Performance | sim/N/A | | GAP: sem k6 |
| Segurança local | sim/N/A | | |
| Acessibilidade | sim/N/A | | N/A: sem UI |
| Mutation | sim/N/A | | GAP: sem mutmut |
| Chaos | sim/N/A | | |
| Carga/stress | sim/N/A | | |
| Visual regression | sim/N/A | | N/A: sem UI |
| Contract | sim/N/A | | |
| Compatibilidade | sim/N/A | | |

Estados (só estes 4): `OK` (rodou, verde) · `FALHOU` (bug/erro TS/vuln que afeta escopo) · `N/A` (fora do projeto) · `GAP` (aplicável mas não rodou: tooling/timeout/orçamento/**harness**/**vuln**).  
**Proibido** “não investigado / pendente / a verificar”. Harness quebrado (alias, import, DB, fixture) = `GAP(harness)`, **não** `OK`.  
**Aplicáveis totais:** N · **OK:** N · **FALHOU:** N · **GAP:** N · **TODO:** deve ser **0**.

**Regra de amarração:** todo bug/erro/vuln/smoke-que-não-rodou citado no relatório precisa apontar para uma linha deste ledger. Bullet solto sem estado = relatório inválido.

---

### 2. Matriz de superfícies (o QUE foi coberto)

| # | Superfície | Coberto? | Teste | Buraco restante |
|---|------------|----------|-------|-----------------|
| 1 | `GET /v1/…` | sim/parcial/não | `test_…::…` | — / falta auth |

**Cobertura do inventário:** X/Y superfícies (Z%).

---

### 3. Contagem honesta

| Métrica | Valor |
|---------|-------|
| Arquivos de teste baseline (lista completa) | N |
| Baseline re-rodada (casos) | XX |
| **Novos nesta rodada** | XX |
| Total executado | XX |
| Passed / Failed / Skipped | XX / XX / XX |
| Bugs encontrados | XX |
| Spot-check mutação (vermelho→verde) | sim N / não |

---

### 4. Evidência bruta (obrigatório)

Comando + exit + sumário + duração de **cada** suíte. Liste todos os arquivos (sem “…” que esconda metade).

```
$ python -m pytest <lista completa> -q --tb=line
NN passed in SS.s
BASELINE_WALL_MS=… EXIT=0

$ python -m pytest <baseline + novos> -q --tb=line
NN passed in SS.s
EXIT=0

$ ruff check <escopo>
All checks passed
WALL_MS=… EXIT=0
```

---

### 5. Bugs

| # | Severidade | Como achou | Descrição | Arquivo | Fix? |
|---|------------|------------|-----------|---------|------|
| 1 | | teste novo / baseline | | | pendente / OK + vermelho→verde |

---

### 6. Gaps (tipos aplicáveis que NÃO rodaram) — cada um com AÇÃO

| Tipo | Motivo (tooling/timeout/orçamento/harness/vuln) | Bloqueia VERDE? | Ação de correção (obrigatória) |
|------|--------------------------------------------------|-----------------|--------------------------------|
| Performance | sem k6 | AMARELO | instalar k6 (com OK) |
| Mutation | sem mutmut | não (Tier 3) | mutmut se pedido |
| Smoke Editor | harness: alias `@/lib` não resolve | **sim** | corrigir path no vitest/tsconfig e re-rodar |
| Dep audit | vuln: `pkg` HIGH | **sim (AMARELO)** | bump/override ou aceite documentado |

Toda linha aqui precisa de **Ação**. `GAP(harness)` e `GAP(vuln)` sem ação = relatório inválido. Se esta tabela tiver linha aplicável, o veredito não pode ser VERDE — COMPLETO.

---

### 7. Spot-check / Mutation

| Trecho | Mutação | Vermelho? | Revertido |
|--------|---------|-----------|-----------|
| | invert `>` | sim/não | sim |

---

### Veredito

- **VERDE — COMPLETO** — todos os aplicáveis `OK`, matriz 100%, ledger sem `TODO`/`GAP`.  
- **AMARELO — PARCIAL** — algum aplicável em `GAP` (liste).  
- **VERMELHO** — bug crítico / baseline quebrada.

Frase factual, sem marketing.

---

### Próximos passos

1. [ ] Fechar `GAP` de tooling (com OK)  
2. [ ] Corrigir bugs (com OK)  
3. [ ] Fechar linhas abertas da matriz  

---

*Gerado por `/full-teste` — ledger, tempos e contagens devem bater com a Evidência bruta.*
