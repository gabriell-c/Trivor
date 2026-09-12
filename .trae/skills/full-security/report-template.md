# Template do Relatório — /full-security

Preencha só com evidência real. Tempo chutado = inválido.  
**Nunca** escreva “sistema 100% seguro”. Use vereditos da tabela abaixo.  
Todo finding/GAP citado no texto deve amarrar a uma linha do ledger.

---

## Relatório de Segurança — [Projeto/Escopo]

**Data:** [YYYY-MM-DD]  
**Escopo:** [repo / módulo]  
**Perfil detectado:** [ex.: FastAPI + Postgres local + Next.js | SPA only | lib PHP]  
**Alvo dinâmico:** [ex.: `http://127.0.0.1:8000` | in-process ASGI | **nenhum — GAP**]  
**Confirmado localhost?** sim / não (se não → dinâmico não rodou)  
**Orçamento:** [~25min | sem teto | Xmin]  
**Wall-clock medido:** [Xm XXs]  
**Modo:** report-only (sem patch sem OK)

---

### Resumo executivo

| Métrica | Valor |
|---------|-------|
| Classes aplicáveis | N |
| SEGURO | N |
| VULNERÁVEL | N |
| N/A | N |
| GAP | N |
| Findings Críticos | N |
| Findings Altos | N |
| Findings Médios/Baixos | N |

**Veredito:** [CRÍTICO / ALTO / SEM FALHAS ENCONTRADAS NA ESTEIRA]

Uma frase factual (ex.: “IDOR em /v1/… explorável em localhost; impacto idêntico em produção se o mesmo código for deployado.”).

---

### 1. Ledger de classes (obrigatório — zero TODO)

Marque **todas** as classes do catálogo (ou agrupe N/A óbvios com motivo único, desde que listados).

| ID | Classe | Aplicável? | Estado | Evidência / motivo |
|----|--------|------------|--------|--------------------|
| A1 | SQL Injection | sim/N/A | SEGURO/VULNERÁVEL/GAP/N/A | |
| A2 | NoSQL Injection | | | |
| A3 | Command Injection | | | |
| A4 | LDAP Injection | | | |
| A5 | XPath Injection | | | |
| A6 | SSTI | | | |
| A7 | Deserialização Insegura | | | |
| A8 | XXE | | | |
| A9 | SSRF | | | |
| A10 | Path Traversal | | | |
| A11 | Mass Assignment | | | |
| A12 | Race Condition | | | |
| A13 | Lógica de Negócio | | | |
| A14 | Broken Access Control | | | |
| A15 | IDOR | | | |
| A16 | Rate Limiting | | | |
| A17 | ReDoS | | | |
| A18 | Insecure Randomness | | | |
| A19 | Timing Attack | | | |
| A20 | Type Juggling | | | |
| A21 | Async Error Handling | | | |
| A22 | Request Smuggling (app) | | | |
| B1 | DB Least Privilege | | | |
| B2 | Campo sensível sem crypto | | | |
| B3 | Debug/dump DB | | | |
| C1 | JWT | | | |
| C2 | CORS | | | |
| C3 | Over-fetching | | | |
| C4 | GraphQL depth | | | |
| C5 | Excessive binding GQL/gRPC | | | |
| C6 | Schema validation | | | |
| C7 | Open Redirect | | | |
| C8 | WebSocket | | | |
| C9 | Cache poisoning/deception | | | |
| D1 | XSS | | | |
| D2 | Prototype Pollution | | | |
| D3 | DOM Clobbering | | | |
| D4 | Clickjacking/CSP | | | |
| D5 | postMessage | | | |
| D6 | Secrets no bundle | | | |
| D7 | Dep client insegura | | | |
| E1 | Mobile local storage | | | |
| E2 | Cert pinning | | | |
| E3 | Deeplink hijacking | | | |
| F1 | Auth fraca | | | |
| F2 | Sessão insegura | | | |
| F3 | Session expiration | | | |
| F4 | CSRF | | | |
| F5 | Keys/IV hardcoded | | | |
| G1 | Secrets hardcoded | | | |
| G2 | Stack/debug leak | | | |
| G3 | Output sanitization | | | |
| G4 | Input validation | | | |
| G5 | Upload malicioso | | | |
| G6 | Deps / supply chain | | | |
| G7 | eval/code injection | | | |
| G8 | Subdomain takeover | | | |

**TODO restantes:** deve ser **0**.  
**Proibido:** “não investigado”.

---

### 2. Findings (por severidade)

Para cada finding:

#### [CRÍTICO|ALTO|MÉDIO|BAIXO] — título curto
- **Classe / ID:** A15 IDOR  
- **CWE / OWASP:** CWE-639 · A01:2021  
- **Evidência:** (código e/ou request/response **mascarando secrets**)  
- **Reprodução em localhost:** passos numerados  
- **Impacto em produção:** o que acontece se o mesmo código estiver deployado  
- **Correção sugerida:** (report-only; não aplicar sem OK)  
- **Linha do ledger:** A15 → VULNERÁVEL

---

### 3. Gaps (com AÇÃO obrigatória)

| ID/Tipo | Motivo (tooling/harness/orçamento/timeout/alvo-remoto/vuln) | Bloqueia dinâmico? | Ação |
|---------|--------------------------------------------------------------|--------------------|------|
| A1 | alvo-remoto: DATABASE_URL=RDS | sim | subir Postgres local / override |
| D1 | harness: front não sobe | sim | `pnpm dev` na porta 3000 |
| G6 | vuln: pkg HIGH | — | bump ou aceite documentado |
| — | tooling: gitleaks ausente | parcial | instalar com OK |

GAP sem ação = relatório inválido.

---

### 4. Evidência bruta (comandos)

```
$ <comando estático>
EXIT=…
(resumo — sem secrets)

$ <probe dinâmico localhost>
EXIT=…
WALL_MS=…
```

---

### 5. O que NÃO foi testado (honestidade)

Localhost **não cobre** (liste o que se aplica):
- [ ] WAF / CDN / Cloudflare
- [ ] Security Groups / VPC / firewall de borda
- [ ] TLS/certificados na edge (Traefik/prod)
- [ ] Rate limit de infraestrutura
- [ ] Dados/volume reais de produção
- [ ] Integrações externas (pagamento, OAuth prod, WhatsApp)
- [ ] Pentest humano avançado / crypto protocol

Estes itens são **fora do escopo desta skill**, não “seguros”.

---

### 6. Próximos passos

1. [ ] Corrigir findings Críticos/Altos (com OK → patch separado)  
2. [ ] Fechar GAPs (harness/alvo local/tooling)  
3. [ ] Re-rodar `/full-security` após fixes  
4. [ ] (Opcional) auditoria de borda/staging com autorização explícita — **outra atividade**, não esta skill sem OK

---

*Gerado por `/full-security` — auto-red-team local, não-destrutivo, report-only.*
