# Catálogo de Tipos de Teste

Referência detalhada de cada tipo de teste: **quando usar, quando NÃO usar, o que valida, e ferramentas**.

---

## 1. Lint + Análise Estática de Tipos

**O que valida:** erros de sintaxe, imports quebrados, tipos incorretos, code smells estáticos.

**Quando usar:** SEMPRE. Primeiro passo, antes de qualquer teste dinâmico.

**Quando NÃO usar:** nunca tem motivo para pular.

**Evidência mínima:** zero erros ou lista de warnings aceitos com justificativa.

**Ferramentas:** ruff, eslint, mypy, pyright, tsc, phpstan, golangci-lint.

---

## 2. Testes Unitários

**O que valida:** uma função/método/classe isolada faz o que promete.

**Quando usar:** SEMPRE. Para toda lógica que não é trivial (if/else, cálculos, transformações, validações).

**Quando NÃO usar:** não teste getters/setters triviais nem código gerado.

**Evidência mínima:** happy path + pelo menos 1 erro/edge case por função.

**Padrão:**
- Input controlado (mocks para deps externas)
- Assertions explícitas (não apenas "não deu erro")
- Nomes descritivos: `test_calcula_desconto_quando_cupom_expirado_retorna_zero`
- **Oráculo** de spec/issue/doc — não copiar o return atual do código (exceto teste `# characterization` rotulado)

---

## 3. Testes de Integração

**O que valida:** módulos cooperam corretamente (API + banco, service + cache, etc.).

**Quando usar:** SEMPRE que houver interação entre camadas (HTTP, DB, filas, cache).

**Quando NÃO usar:** não substitua unit por integração — são complementares.

**Evidência mínima:** request HTTP real → response correta + efeitos no banco verificados.

**Padrão:**
- Banco real ou container (não SQLite para testar Postgres)
- Limpar estado entre testes (transaction rollback ou truncate)
- Testar cascade (criar → ler → atualizar → deletar)

---

## 4. Testes E2E (End-to-End)

**O que valida:** jornada completa do usuário funciona ponta a ponta.

**Quando usar:** SEMPRE para jornadas críticas (signup, compra, CRUD principal).

**Quando NÃO usar:** não faça E2E para cada variação de input — isso é unit/property.

**Evidência mínima:** pelo menos 1 jornada happy + 1 jornada de erro por feature.

**Padrão:**
- Simula o usuário real (browser para frontend, HTTP sequencial para API)
- Verifica estado final (DB, tela, email enviado)
- Sem mocks de infra (se possível) — se mockear, declare no relatório

---

## 5. Smoke Tests / Sanity

**O que valida:** app sobe, rotas respondem, não há crash catastrófico.

**Quando usar:** SEMPRE como gate rápido antes dos testes pesados.

**Quando NÃO usar:** não conte como "testado" — é apenas sanidade básica. Smoke que só lê fontes TS (`node:test` estático) **não** substitui E2E de browser nem jornada HTTP.

**Evidência mínima:** health endpoint 200, home renderiza, não há console.error.

---

## 6. Testes de Regressão

**O que valida:** bugs corrigidos não voltam + funcionalidades existentes não quebraram.

**Quando usar:** toda vez que mudar código que já tinha testes. Incluir caso para cada bug fix.

**Quando NÃO usar:** se o escopo é greenfield sem histórico.

**Evidência mínima:** snapshot antes/depois; ou suíte pre-existente roda verde.

---

## 7. Property-Based Testing (teste generativo)

**O que valida:** invariantes se mantêm para QUALQUER input válido (não só os que você imaginou).

**Quando usar:**
- Parsers, serializers, encoders/decoders
- Funções matemáticas ou de transformação
- Validadores de input
- Qualquer lugar onde "pra todo X, vale Y"

**Quando NÃO usar:** UI pura, testes de fluxo de negócio (que dependem de sequência).

**Evidência mínima:** propriedade declarada + N runs (min 100 exemplos).

**Ferramentas:** hypothesis (Python), fast-check (JS/TS), PropEr (Elixir), quickcheck.

**Exemplo de propriedade:**
- `parse(serialize(x)) == x` (roundtrip)
- `len(filter(items, pred)) <= len(items)` (não cria elementos)
- `validate(random_valid_input) == True` (gerador de inputs)

---

## 8. Fuzzing

**O que valida:** o código não crasha com inputs inesperados/malformados.

**Quando usar:**
- Parsers (JSON, XML, CSV, query strings)
- Endpoints que aceitam upload/body complexo
- Qualquer código que processa input externo não-confiável

**Quando NÃO usar:** lógica interna com inputs já validados upstream.

**Evidência mínima:** N iterações sem crash (min 1000); ou crash encontrado e reportado.

**Ferramentas:** hypothesis (Python), atheris (Python, libFuzzer), radamsa, fast-check (JS), go fuzz.

---

## 9. Testes de Concorrência / Race Condition

**O que valida:** estado compartilhado não corrompe sob acesso paralelo.

**Quando usar:**
- Counters, saldos, estoques
- Jobs que podem executar em paralelo
- Qualquer endpoint que faz read-modify-write
- Cache invalidation
- WebSocket / real-time

**Quando NÃO usar:** endpoints puramente stateless sem efeitos colaterais.

**Evidência mínima:** N requests/ops paralelas (50+) → estado final consistente **sem** serializar artificialmente o caminho crítico.

**Padrão:**
```python
# Python — paralelismo no código real (sem Lock no mock do claim)
results = await asyncio.gather(*[transfer(conta, 1) for _ in range(100)])
assert saldo_final == saldo_inicial - 100

# JS
const results = await Promise.all(Array(100).fill().map(() => fetch(...)))
```

**NÃO conta como teste de race:**
- Colocar `asyncio.Lock` / mutex no mock para “passar”
- Chamar função pura N vezes em paralelo (sem estado compartilhado mutável)
- Só `Promise.all` em GETs idempotentes sem efeito colateral

---

## 10. Testes de Performance / Carga / Stress

**O que valida:** resposta dentro de SLA sob carga normal e extrema.

**Quando usar:**
- APIs com SLA de latência
- Páginas com LCP/FCP target
- Queries que podem ser N+1
- Endpoints que escalam com dados

**Quando NÃO usar:** protótipos/MVPs sem SLA definido (registre como gap, não pule silenciosamente).

**Evidência mínima:**
- p50, p95, p99 de latência
- Throughput (req/s)
- Error rate sob carga
- Memory/CPU durante o teste

**Cenários:**
- **Load:** carga esperada por 60s
- **Stress:** 2-5x a carga esperada
- **Spike:** burst de 0 a max em 5s
- **Soak:** carga moderada por 10+ min (detecta memory leak)

---

## 11. Mutation Testing

**O que valida:** seus testes realmente detectam mudanças no código (não são "testes verdes que não testam nada").

**Quando usar:**
- Quando cobertura está alta (>80%) mas você duvida da qualidade
- Validadores, réguas, cálculos críticos
- Antes de declarar "suíte completa"

**Quando NÃO usar:**
- Se não tem test runner configurado (primeiro escreva testes, depois mute)
- Em código trivial (boilerplate, config)

**Evidência mínima:** MSI (Mutation Score Indicator) ≥ 70%.

**Ferramentas:** mutmut (Python), stryker (JS/TS), infection (PHP), go-mutesting.

---

## 12. Testes de Segurança

**O que valida:** app não é vulnerável a ataques comuns.

**Quando usar:** SEMPRE para apps que recebem input de usuários ou estão expostas na web.

**Checklist mínimo:**
- SQL injection (inputs → queries)
- XSS (inputs → HTML renderizado)
- IDOR (acessar recurso de outro usuário trocando ID)
- Auth bypass (rotas protegidas sem token)
- CSRF (mutations sem token CSRF)
- Path traversal (uploads, file read)
- Mass assignment (enviar campos extras no body)

**Ferramentas:** bandit, semgrep, eslint-plugin-security, OWASP ZAP (local). sqlmap só com OK explícito e alvo local.

**SEGURANÇA OBRIGATÓRIA:** ferramentas ofensivas (ZAP, sqlmap, schemathesis, nikto) rodam **EXCLUSIVAMENTE** contra:
- `localhost` / `127.0.0.1`
- Containers Docker locais do projeto
- Ambientes de teste explicitamente autorizados pelo usuário

**NUNCA** apontar para produção, staging externo ou domínio de terceiros sem autorização explícita. Violação disso é risco legal e operacional.

---

## 13. Testes de Acessibilidade

**O que valida:** app é usável por pessoas com deficiência (leitores de tela, teclado, contraste).

**Quando usar:** todo app frontend com usuários públicos.

**Quando NÃO usar:** APIs puras, ferramentas CLI internas.

**Evidência mínima:** zero violações WCAG A; warnings de AA listados.

**Ferramentas:** axe-core, pa11y, lighthouse accessibility score, playwright accessibility.

---

## 14. Visual Regression

**O que valida:** UI não mudou visualmente sem intenção.

**Quando usar:** após mudanças de CSS, componentes, temas, refactors de layout.

**Quando NÃO usar:** backend puro; ou se não há baseline (crie o baseline primeiro).

**Evidência mínima:** screenshots antes/depois; diff com threshold aceitável.

**Ferramentas:** playwright screenshots + comparação, chromatic, percy, backstop.js.

---

## 15. Contract Testing

**O que valida:** API não quebra contratos com consumers (frontend, mobile, outros services).

**Quando usar:**
- APIs consumidas por múltiplos clients
- Mudanças de schema/response
- Microservices

**Quando NÃO usar:** monolitos com um único consumer no mesmo repo (integração resolve).

**Ferramentas:** schemathesis (OpenAPI → testes automáticos), pact, dredd.

---

## 16. Chaos Engineering

**O que valida:** sistema se recupera de falhas de infraestrutura.

**Quando usar:**
- Apps distribuídas (microservices, filas, cache)
- Quando há retry/circuit-breaker implementado
- Antes de ir pra produção em alta disponibilidade

**Quando NÃO usar:**
- App monolítica local em dev
- Se não há mecanismo de recuperação (primeiro implemente, depois teste)

**Cenários:**
- Kill container do banco → app retorna erro gracioso?
- Latência 3s no cache → fallback funciona?
- DNS falha → retry conecta?

**Ferramentas:** toxiproxy, docker stop/kill, tc (traffic control linux), chaos-monkey.

---

## 17. Testes de Compatibilidade

**O que valida:** funciona em diferentes ambientes/versões.

**Quando usar:**
- Bibliotecas públicas (testar em múltiplas versões de runtime)
- Frontend (múltiplos browsers)
- Mobile (múltiplos devices)

**Quando NÃO usar:** app interna com ambiente controlado (1 browser, 1 versão Node).

**Ferramentas:** tox (Python, múltiplas versões), nox, playwright multi-browser, BrowserStack.

---

## Resumo de prioridade

| Prioridade | Tipo | Justificativa |
|-----------|------|---------------|
| 1 (sempre) | Lint/types + Unit + Integração + E2E + Smoke | Base mínima, sem isso não tem qualidade |
| 2 (profundo) | Regressão + Property + Fuzz + Race + Perf + Segurança + A11y | Encontra bugs que unit não pega |
| 3 (máximo) | Mutation + Chaos + Visual + Contract + Compatibilidade | Validação de maturidade da suíte |
