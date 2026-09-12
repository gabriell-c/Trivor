# Catálogo de Ataques — /full-security

Para cada classe: **quando APLICÁVEL / N/A**, método (**S**=estático, **D**=dinâmico localhost, **H**=híbrido), evidência mínima, severidade típica, CWE/OWASP.

Estados no ledger: `SEGURO | VULNERÁVEL | N/A | GAP`.

---

## A. Backend / Lógica de aplicação

### A1. SQL Injection
- **APLICÁVEL:** app fala com SQL (Postgres/MySQL/SQLite/…).
- **N/A:** sem DB SQL.
- **Método:** H — S: concat de query, f-string/SQL cru; D: `' OR 1=1`, boolean/time-based **não-destrutivo**.
- **Evidência:** request que altera resultado indevido **ou** código que concatena input.
- **Sev / CWE:** Crítico · CWE-89 · A03:2021

### A2. NoSQL Injection
- **APLICÁVEL:** Mongo/Redis query builders com input.
- **N/A:** só SQL relacional.
- **Método:** H — operadores `$gt`/`$ne`, JSON injection.
- **Sev / CWE:** Crítico · CWE-943 · A03

### A3. Command Injection
- **APLICÁVEL:** `os.system`, `exec`, `subprocess` com shell, backticks.
- **N/A:** sem execução de shell.
- **Método:** H — S: acha sink; D: payload `; id` / `&&` só se sandbox local seguro.
- **Sev / CWE:** Crítico · CWE-78 · A03

### A4. LDAP Injection
- **APLICÁVEL:** auth/busca LDAP.
- **N/A:** sem LDAP.
- **Método:** H · CWE-90 · Alto/Crítico

### A5. XPath Injection
- **APLICÁVEL:** XML + XPath com input.
- **N/A:** sem XPath.
- **Método:** H · CWE-643 · Alto

### A6. SSTI (Server-Side Template Injection)
- **APLICÁVEL:** Jinja/Twig/EJS/Freemarker renderiza input.
- **N/A:** templates só estáticos/compilados sem user input.
- **Método:** H — `{{7*7}}` / polaris seguros.
- **Sev / CWE:** Crítico · CWE-1336 · A03

### A7. Deserialização Insegura
- **APLICÁVEL:** `pickle`, `unserialize`, Java/`ObjectInputStream`, YAML `load` inseguro.
- **N/A:** só JSON tipado/Pydantic sem unpickle.
- **Método:** S (+ D controlado) · CWE-502 · Crítico

### A8. XXE
- **APLICÁVEL:** parser XML com entidades externas.
- **N/A:** sem XML ou parser seguro (defusedxml, etc.).
- **Método:** H · CWE-611 · Alto/Crítico

### A9. SSRF
- **APLICÁVEL:** server busca URL/host a partir de input (webhooks, preview, scrape).
- **N/A:** sem fetch server-side de URL user-controlled.
- **Método:** H — tentar `http://127.0.0.1` / metadata **só** em lab local; não atacar redes externas.
- **Sev / CWE:** Alto/Crítico · CWE-918 · A10

### A10. Path Traversal / Directory Traversal
- **APLICÁVEL:** download/upload/read file por path/nome.
- **N/A:** sem I/O de arquivo user-influenced.
- **Método:** H — `../`, encoding; ler só arquivo marcador inócuo.
- **Sev / CWE:** Alto/Crítico · CWE-22 · A01

### A11. Mass Assignment
- **APLICÁVEL:** body vira model/ORM sem allowlist de campos.
- **N/A:** DTOs estritos / schema freeze.
- **Método:** H — enviar `role=admin`, `is_admin=true`, preço.
- **Sev / CWE:** Alto · CWE-915 · A08

### A12. Race Condition
- **APLICÁVEL:** saldo, estoque, claim, cupom one-shot, estado compartilhado.
- **N/A:** só leitura / stateless.
- **Método:** D — N requests paralelos; assert invariante.
- **Sev / CWE:** Alto · CWE-362 · A04

### A13. Lógica de Negócio Falha
- **APLICÁVEL:** checkout, cupom, preço, etapas de wizard, pagamentos.
- **N/A:** CRUD sem regras financeiras/fluxo.
- **Método:** D — pular passo, reusar cupom, alterar preço no client.
- **Sev / CWE:** Alto/Crítico · CWE-840 · A04

### A14. Broken Access Control
- **APLICÁVEL:** roles, RBAC, rotas protegidas.
- **N/A:** app 100% pública sem auth.
- **Método:** H — acessar rota admin sem papel.
- **Sev / CWE:** Crítico · CWE-284 · A01

### A15. IDOR
- **APLICÁVEL:** IDs em URL/body (UUID/int) multi-tenant ou multi-user.
- **N/A:** sem objetos por ID / single-user local sem tenants.
- **Método:** D — trocar `id`/`workspace` de outro recurso.
- **Sev / CWE:** Crítico · CWE-639 · A01

### A16. Rate Limiting Ausente
- **APLICÁVEL:** login, OTP, APIs públicas, reset senha.
- **N/A:** CLI interna sem rede.
- **Método:** D — rajada controlada; medir se bloqueia.
- **Sev / CWE:** Médio/Alto · CWE-770 · A04

### A17. ReDoS
- **APLICÁVEL:** regex em input user-controlled.
- **N/A:** regex só em constantes internas.
- **Método:** S (+ D se seguro) · CWE-1333 · Médio/Alto

### A18. Insecure Randomness
- **APLICÁVEL:** tokens, senhas temporárias, reset links, API keys geradas.
- **N/A:** RNG só pra UI/cores.
- **Método:** S — `Math.random`/`random.random` vs CSPRNG.
- **Sev / CWE:** Alto · CWE-330 · A02

### A19. Timing Attack
- **APLICÁVEL:** comparação de secrets/tokens com `==` não constant-time.
- **N/A:** sem comparação de segredo.
- **Método:** S (preferencial); D estatístico só se viável no orçamento.
- **Sev / CWE:** Médio · CWE-208 · A02

### A20. Type Confusion / Type Juggling
- **APLICÁVEL:** PHP `==`, JS coerção frouxa em auth/flags.
- **N/A:** tipagem estrita sem comparação frouxa em segurança.
- **Método:** H · CWE-843 · Alto

### A21. Improper Error Handling (async)
- **APLICÁVEL:** promises/futures sem catch; erros vazam estado/stack.
- **N/A:** sync-only sem async.
- **Método:** S · CWE-755 · Médio

### A22. HTTP Request Smuggling (app parsing)
- **APLICÁVEL:** app faz parse manual de HTTP/chunked/CL frente a proxy.
- **N/A:** framework padrão atrás de um único proxy bem configurado e sem parse manual.
- **Método:** S (+ D avançado se tooling/orçamento) · CWE-444 · Alto
- **Nota:** smuggling clássico de borda (proxy↔origin) frequentemente `GAP` em localhost — documentar.

---

## B. Banco de dados

### B1. Least Privilege ausente
- **APLICÁVEL:** app conecta a DB.
- **N/A:** sem DB.
- **Método:** S — user da connection string é `root`/`postgres`/`sa` / superuser; grants excessivos.
- **Sev / CWE:** Alto · CWE-250 · A05

### B2. Dados sensíveis sem criptografia de campo
- **APLICÁVEL:** PII, tokens, senhas, cartões em colunas.
- **N/A:** sem dados sensíveis persistidos.
- **Método:** S — senha em plain, tokens raw; falta Fernet/KMS/hash.
- **Sev / CWE:** Alto/Crítico · CWE-311 · A02

### B3. Rota de debug/dump de banco
- **APLICÁVEL:** endpoints `/debug`, dump SQL, adminer embutido no código.
- **N/A:** sem rotas de debug.
- **Método:** H · CWE-489 · Alto/Crítico

---

## C. API

### C1. JWT mal implementado
- **APLICÁVEL:** JWT/JWS/JWE.
- **N/A:** só session cookie server-side / API key simples.
- **Método:** H — `alg=none`, key confusion, sem `exp`, sem verify.
- **Sev / CWE:** Crítico · CWE-347 · A02/A07

### C2. CORS Misconfigurado
- **APLICÁVEL:** API browser-facing.
- **N/A:** API só server-to-server sem CORS.
- **Método:** H — `ACA-Origin: *` + credentials; origin reflection.
- **Sev / CWE:** Alto · CWE-942 · A05

### C3. Over-fetching / exposição excessiva
- **APLICÁVEL:** serializers/responses amplos.
- **N/A:** respostas mínimas comprovadas.
- **Método:** H — response traz hash, PII, campos internos.
- **Sev / CWE:** Médio/Alto · CWE-200 · A01

### C4. GraphQL — profundidade/complexidade
- **APLICÁVEL:** GraphQL.
- **N/A:** sem GraphQL.
- **Método:** H — query aninhada profunda / batch.
- **Sev / CWE:** Alto · CWE-770 · A04

### C5. Excessive Data Binding (GraphQL/gRPC)
- **APLICÁVEL:** GraphQL/gRPC com input → model amplo.
- **N/A:** sem GraphQL/gRPC.
- **Método:** H · CWE-915 · Alto

### C6. Validação de Schema Ausente
- **APLICÁVEL:** body/query sem schema (Pydantic/Zod/Marshmallow).
- **N/A:** validação estrita em todas as entradas.
- **Método:** S · CWE-20 · Médio/Alto

### C7. Open Redirect
- **APLICÁVEL:** `?next=`, `redirect=`, `return_url`.
- **N/A:** sem redirects user-controlled.
- **Método:** H — `//evil.com` / URL absoluta externa.
- **Sev / CWE:** Médio · CWE-601 · A01

### C8. WebSocket Inseguro
- **APLICÁVEL:** WS/Socket.IO.
- **N/A:** sem WS.
- **Método:** H — connect sem auth; origin livre.
- **Sev / CWE:** Alto · CWE-1385 · A01/A07

### C9. Cache Poisoning / Web Cache Deception
- **APLICÁVEL:** cache HTTP/CDN headers controláveis; rotas confusas.
- **N/A:** sem cache compartilhado.
- **Método:** S (+ D se cache local) · CWE-444/CWE-525 · Médio/Alto
- **Nota:** muito de CDN = `GAP` em localhost puro.

---

## D. Frontend / Client-side

### D1. XSS (Refletido / Armazenado / DOM)
- **APLICÁVEL:** UI web renderiza input.
- **N/A:** sem frontend.
- **Método:** H — sinks `innerHTML`, `dangerouslySetInnerHTML`, templates; payloads locais.
- **Sev / CWE:** Alto/Crítico · CWE-79 · A03

### D2. Prototype Pollution
- **APLICÁVEL:** JS merge/deep assign de objetos user-influenced.
- **N/A:** sem JS dinâmico / merges seguros.
- **Método:** S · CWE-1321 · Alto

### D3. DOM Clobbering
- **APLICÁVEL:** DOM + ids/names que sobrescrevem globals.
- **N/A:** sem DOM.
- **Método:** S · CWE-791 · Médio

### D4. Clickjacking / falta de CSP-frame
- **APLICÁVEL:** UI sensível (login, ações).
- **N/A:** sem UI.
- **Método:** H — `X-Frame-Options`/`frame-ancestors` ausentes.
- **Sev / CWE:** Médio · CWE-1021 · A05

### D5. postMessage Inseguro
- **APLICÁVEL:** `window.postMessage` / listeners.
- **N/A:** sem postMessage.
- **Método:** S — listener sem checar `event.origin`.
- **Sev / CWE:** Alto · CWE-346 · A01

### D6. Segredos no bundle JS
- **APLICÁVEL:** build front.
- **N/A:** sem bundle.
- **Método:** S — grep em `.next`/`dist` por keys/API secrets.
- **Sev / CWE:** Alto/Crítico · CWE-798 · A02

### D7. Dependência de terceiro insegura (client)
- **APLICÁVEL:** scripts CDN / deps front.
- **N/A:** sem front.
- **Método:** S — audit + SRI ausente em CDN.
- **Sev / CWE:** Médio/Alto · CWE-1104 · A06

---

## E. Mobile / híbrido (se aplicável)

### E1. Insecure Local Storage
- **APLICÁVEL:** RN/Capacitor/Flutter com storage.
- **N/A:** sem mobile.
- **Método:** S — tokens em AsyncStorage/SharedPreferences plain.
- **Sev / CWE:** Alto · CWE-922 · A02

### E2. Certificate Pinning Ausente
- **APLICÁVEL:** app mobile falando HTTPS sensível.
- **N/A:** sem mobile / só web.
- **Método:** S · CWE-295 · Médio (contexto)
- **Nota:** ausência ≠ sempre bug; documentar risco MITM.

### E3. Deep Link Hijacking
- **APLICÁVEL:** deeplinks/universal links.
- **N/A:** sem deeplink.
- **Método:** S · CWE-940 · Alto

---

## F. Autenticação / Sessão (transversal)

### F1. Falhas de Autenticação
- **APLICÁVEL:** login/senha/OTP.
- **N/A:** sem auth.
- **Método:** H — senha fraca aceita, sem lockout, MFA ausente em área sensível.
- **Sev / CWE:** Alto/Crítico · CWE-287 · A07

### F2. Gestão de Sessão Insegura
- **APLICÁVEL:** cookies/tokens de sessão.
- **N/A:** sem sessão.
- **Método:** H — token previsível, sem HttpOnly/Secure/SameSite.
- **Sev / CWE:** Alto · CWE-384 · A07

### F3. Insufficient Session Expiration
- **APLICÁVEL:** sessões longas / JWT sem `exp` / logout não invalida.
- **N/A:** tokens de curta duração com denylist ok.
- **Método:** H · CWE-613 · Médio/Alto

### F4. CSRF
- **APLICÁVEL:** cookie-session + state-changing.
- **N/A:** Bearer-only sem cookies; ou SameSite+token ok.
- **Método:** H · CWE-352 · Alto · A01

### F5. Hardcoded Crypto Keys / IV Reutilizado
- **APLICÁVEL:** crypto no código.
- **N/A:** sem crypto app-level.
- **Método:** S — key/IV fixos no repo.
- **Sev / CWE:** Crítico · CWE-321/CWE-329 · A02

---

## G. Geral / Cross-cutting

### G1. Vazamento de Segredos Hardcoded
- **APLICÁVEL:** quase sempre.
- **Método:** S — gitleaks/trufflehog/grep (AWS keys, tokens, `.env` commitado).
- **Sev / CWE:** Crítico · CWE-798 · A02
- **Cuidado:** não ecoar o secret completo no relatório — mascare.

### G2. Stack Trace / Debug Info Exposto
- **APLICÁVEL:** HTTP API/UI.
- **Método:** H — 500 com traceback; `DEBUG=True` em config “local” que pode vazar.
- **Sev / CWE:** Médio · CWE-209 · A05

### G3. Sanitização de Saída Ausente
- **APLICÁVEL:** HTML/email/PDF gerados com input.
- **Método:** S · CWE-116 · Alto

### G4. Validação de Entrada Ausente
- **APLICÁVEL:** endpoints/forms.
- **Método:** S · CWE-20 · Médio/Alto

### G5. Upload de Arquivo Malicioso
- **APLICÁVEL:** upload.
- **N/A:** sem upload.
- **Método:** H — extensão/MIME/path; **não** gravar malware real; usar eicar/polyglot inócuo ou só validar rejeição.
- **Sev / CWE:** Alto/Crítico · CWE-434 · A04

### G6. Dependência Vulnerável / Supply Chain
- **APLICÁVEL:** sempre que há lockfile.
- **Método:** S — `npm audit`/`pip-audit`/`composer audit`/`govulncheck`.
- **Sev / CWE:** variável · CWE-1104 · A06
- **Regra:** HIGH/CRITICAL → estado terminal + ação (nunca “não investigado”).

### G7. eval() / Code Injection Dinâmico
- **APLICÁVEL:** `eval`, `Function(`, `exec`, dynamic `import` de string user.
- **Método:** S · CWE-95 · Crítico

### G8. Subdomain Takeover (código/DNS)
- **APLICÁVEL:** referências a hosts/CNAME em código/config.
- **N/A:** monólito sem DNS externos.
- **Método:** S — dangling CNAME/apontamentos; verificação DNS ativa só se usuário autorizar e for domínio **dele**.
- **Sev / CWE:** Alto · CWE-284 · A05
- **Nota:** probe DNS externo = só com OK; senão `GAP` ou achado só estático.

---

## Extensível

Para nova classe, copie o bloco:

```markdown
### XN. Nome
- **APLICÁVEL:** …
- **N/A:** …
- **Método:** S|D|H — como provar (não-destrutivo, local)
- **Evidência:** …
- **Sev / CWE:** … · CWE-… · OWASP …
```

Atualize o ledger do relatório e a tabela de seleção no `SKILL.md` se for grupo novo.

---

## Prioridade sugerida na esteira (aplicáveis)

1. G1 Secrets · G6 Deps · F5 Keys · A14/A15 Access/IDOR · C1 JWT  
2. A1–A10 Injections/SSRF/Path · A11 Mass assign · B1–B3 DB  
3. C2 CORS · F1–F4 Auth/CSRF · A12 Race · A13 Business logic  
4. D* Frontend · C4–C9 API avançada · E* Mobile · A16–A22 resto  
5. Scanners pesados (ZAP/sqlmap) se tooling + orçamento  

Sempre respeite N/A e guardrails localhost do `SKILL.md`.
