# Template do Relatório — /performance-teste

Use este template após a auditoria. Copie e preencha.

---

## Auditoria de Boas Práticas — [Projeto/Escopo]

**Data:** [YYYY-MM-DD]
**Escopo:** [rota/módulo/projeto inteiro]
**Modo:** [completo | performance | escalabilidade | legibilidade | arquitetura]
**Stack:** [Python/FastAPI | Next.js/React | etc.]

---

### Resumo Executivo

| Métrica | Valor |
|---------|-------|
| Total de achados | XX |
| CRÍTICO | XX |
| ALTO | XX |
| MÉDIO | XX |
| BAIXO | XX |
| INFO | XX |
| Quick wins (alto impacto + baixo esforço) | XX |
| Gaps (sem ferramenta para medir) | XX |

**Veredito:** [VERDE — código saudável | AMARELO — dívidas aceitáveis | VERMELHO — problemas graves]

---

### Achados por Eixo

#### Performance Backend

| # | Sev. | Localização | Evidência | Sugestão | Esforço |
|---|------|-------------|-----------|----------|---------|
| 1 | | `arquivo:linha` | | | Baixo/Médio/Alto |

#### Performance Frontend

| # | Sev. | Localização | Evidência | Sugestão | Esforço |
|---|------|-------------|-----------|----------|---------|
| | | | | | |

#### Escalabilidade

| # | Sev. | Localização | Evidência | Sugestão | Esforço |
|---|------|-------------|-----------|----------|---------|
| | | | | | |

#### Legibilidade

| # | Sev. | Localização | Evidência | Sugestão | Esforço |
|---|------|-------------|-----------|----------|---------|
| | | | | | |

#### Manutenibilidade

| # | Sev. | Localização | Evidência | Sugestão | Esforço |
|---|------|-------------|-----------|----------|---------|
| | | | | | |

#### Arquitetura

| # | Sev. | Localização | Evidência | Sugestão | Esforço |
|---|------|-------------|-----------|----------|---------|
| | | | | | |

---

### Quick Wins (alto impacto + baixo esforço)

| # | Achado | Impacto esperado |
|---|--------|-----------------|
| | | |

---

### Medições Realizadas

| O que mediu | Ferramenta | Resultado |
|-------------|-----------|-----------|
| Queries por endpoint | | X queries em GET /path |
| Bundle size | | XX KB (rota /path) |
| Complexidade | | func() = XX (radon/eslint) |
| Código morto | | XX imports não usados |
| Duplicação | | XX blocos duplicados |
| `any` count | | XX ocorrências |

---

### Gaps Honestos

| Eixo | O que não mediu | Motivo | Como resolver |
|------|----------------|--------|---------------|
| | | [ferramenta não instalada / não aplicável] | [instalar X / config Y] |

---

### Antes vs Depois (se aplicou correções)

| Achado | Métrica | Antes | Depois | Delta |
|--------|---------|-------|--------|-------|
| | | | | |

Se não aplicou correções, esta seção fica vazia (auditoria read-only).

---

### Próximos Passos

1. [ ] [Quick wins a aplicar]
2. [ ] [Dívidas a planejar na sprint]
3. [ ] [Ferramentas a instalar para medir melhor]
4. [ ] [Eixos que ficaram como gap]

---

*Gerado por `/performance-teste`*
