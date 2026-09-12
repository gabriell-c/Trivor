# Catálogo de Eixos de Auditoria

Referência detalhada de cada eixo: **o que medir, como medir, o que é achado real vs ruído, e severidade típica**.

Regra universal: **sem evidência (número, localização, medição) = não entra no relatório**.

---

## 1. Performance Backend

### O que procurar

| Problema | Como detectar | Severidade típica |
|----------|--------------|-------------------|
| **N+1 queries** | Log SQL com contagem por request; lazy loading sem eager | CRÍTICO se >5 queries extras |
| **Queries sem índice** | `EXPLAIN ANALYZE` mostrando Seq Scan em tabela >1K linhas | ALTO |
| **`SELECT *`** | Grep no ORM; buscando mais colunas que o necessário | MÉDIO |
| **Serialização pesada** | Serializar modelo inteiro quando a rota precisa de 3 campos | MÉDIO |
| **Chamada síncrona bloqueante** | HTTP externo / file I/O no request handler sem async/thread | ALTO |
| **Sem paginação** | `query.all()` / `.find()` sem limit em endpoint de listagem | CRÍTICO se tabela cresce |
| **Pool de conexão inadequado** | Pool pequeno (ex: 5) com muitos workers | ALTO |
| **Cache ausente** | Query pesada idêntica a cada request, sem TTL | MÉDIO-ALTO |
| **Retry sem backoff** | Chamada externa com retry infinito ou sem exponential backoff | ALTO |
| **JSON pesado na response** | Resposta > 1 MB para listagem | MÉDIO |

### Evidência mínima por achado

- **N+1:** "GET /produtos gera 14 queries (1 base + 13 lazy para `itens.categorias`)"
- **Sem índice:** "EXPLAIN mostra Seq Scan em `pedidos` (12K rows), coluna `status`"
- **Sem paginação:** "`produtos.py:89` faz `query.all()` sem limit — tabela tem 3K registros"

### O que NÃO é achado de performance backend

- "O código poderia ser mais rápido" (sem medição)
- "Essa query parece lenta" (sem EXPLAIN)
- Micro-otimizações (trocar `for` por list comprehension sem impacto mensurável)

---

## 2. Performance Frontend

### O que procurar

| Problema | Como detectar | Severidade típica |
|----------|--------------|-------------------|
| **Bundle pesado** | `next build` / `vite build` mostrando rota > 150 KB JS | ALTO |
| **Import pesado desnecessário** | Lib inteira importada quando só usa 1 função (ex: lodash, moment) | MÉDIO |
| **Import de dev em prod** | fast-check, faker, test utils no bundle de produção | ALTO |
| **Re-renders excessivos** | Componente renderiza em todo poll/state change sem necessidade | ALTO se lista grande |
| **Props instáveis** | Objeto literal / arrow function no JSX de lista | MÉDIO |
| **Context amplo demais** | Um Provider que causa re-render de toda a árvore | ALTO |
| **Imagens sem otimização** | PNG/JPG > 200 KB sem next/image ou similar | MÉDIO |
| **Sem lazy loading** | Componente pesado (chart, editor) carregado no initial bundle | MÉDIO |
| **Waterfall de data** | Componente filho faz fetch que depende do fetch do pai, em série | ALTO |
| **CSS não utilizado** | Classes/imports de CSS que não existem no markup | BAIXO |
| **Layout shift** | Imagens/componentes sem dimensão explícita | MÉDIO |

### Evidência mínima por achado

- **Bundle:** "Rota `/produtos` — First Load JS: 187 KB (meta: <130 KB)"
- **Re-render:** "`ProdutosLista.tsx:23` — useProdutos() retorna referência nova a cada 5s poll → 30 cards re-renderizam"
- **Import pesado:** "`page.tsx:3` importa `fast-check` (42 KB) mas não usa em runtime"

### O que NÃO é achado de performance frontend

- "Deveria usar useMemo" (sem evidência de re-render real)
- "Essa imagem parece grande" (sem checar o tamanho real)
- "Tailwind gera CSS demais" (purge já remove)

---

## 3. Escalabilidade

### O que procurar

| Problema | Como detectar | Severidade típica |
|----------|--------------|-------------------|
| **Sem paginação** | Listagem retorna tudo — funciona com 10, quebra com 10K | CRÍTICO |
| **`SELECT *` em tabela grande** | Busca todas as colunas quando precisa de 3 | MÉDIO |
| **Job síncrono bloqueante** | Processamento pesado no request handler (não fila) | ALTO |
| **Cache ausente em hot path** | Query pesada a cada request sem TTL/Redis | ALTO |
| **Estado global mutável** | Variável de módulo compartilhada entre requests (Python) / entre renders (React) | CRÍTICO |
| **Upload em memória** | `request.body` carrega arquivo inteiro na RAM | ALTO se aceita >10 MB |
| **Sem connection pooling** | Abre/fecha conexão a cada request | ALTO |
| **Lock global** | Mutex/semáforo que serializa todos os requests | CRÍTICO |
| **Sem rate limiting** | Endpoint público sem throttle | MÉDIO (cobre security skill) |
| **Broadcast sem filtro** | WebSocket/SSE envia tudo para todos | ALTO com >10 clients |

### Evidência mínima

- "Service `checkout.py:200` processa pagamento inline (~3s) — deveria ser job async"
- "Variável `_cache = {}` em `estoque.py:1` — compartilhada entre requests do worker"

---

## 4. Legibilidade

### O que procurar

| Problema | Como detectar | Severidade típica |
|----------|--------------|-------------------|
| **Complexidade ciclomática alta** | radon / eslint complexity > 10 | MÉDIO |
| **Função gigante** | > 50 linhas (Python/TS) ou > 80 linhas (componente React) | MÉDIO |
| **Aninhamento profundo** | > 3 níveis de if/for/try | MÉDIO |
| **Arquivo gigante** | > 400 linhas | MÉDIO |
| **Nomes inconsistentes** | `get_data` vs `fetchItems` vs `load_stuff` no mesmo repo | BAIXO |
| **Nomes genéricos** | `data`, `result`, `temp`, `item`, `obj`, `val` em escopo amplo | BAIXO |
| **Comentários mentirosos** | Comentário diz uma coisa, código faz outra | ALTO |
| **Código comentado** | Blocos inteiros de código em comentário | BAIXO |
| **Magic numbers** | `if retries > 3` / `limit=50` sem constante nomeada | BAIXO |
| **Boolean trap** | `process(data, True, False, True)` sem named args | MÉDIO |

### Evidência mínima

- "`produtos_service.py:45` — `calcular_preco()` tem complexidade ciclomática 18 (radon)"
- "`dashboard.tsx` — 520 linhas, 3 responsabilidades (fetch + render + cálculo)"

### O que NÃO é achado de legibilidade

- Estilo pessoal ("eu prefiro X ao Y") sem impacto em compreensão
- Formatação (isso é lint, não auditoria)
- "Variável poderia ser mais descritiva" sem dizer qual e por quê

---

## 5. Manutenibilidade

### O que procurar

| Problema | Como detectar | Severidade típica |
|----------|--------------|-------------------|
| **Código morto** | Imports não usados, exports não consumidos, funções nunca chamadas | MÉDIO |
| **Duplicação real** | Mesmo bloco (>5 linhas) em 2+ lugares | MÉDIO-ALTO |
| **`any` em TypeScript** | `rg ":\s*any\b" --type ts -c` | MÉDIO |
| **Schema frouxo** | Pydantic model com `dict` / `Any` onde deveria ter tipo | MÉDIO |
| **Acoplamento forte** | Service importa diretamente de outro service (não via interface/protocol) | MÉDIO |
| **Dependência circular** | A importa B que importa A | ALTO |
| **Config hardcoded** | URLs, timeouts, limites enterrados no código | MÉDIO |
| **Sem type hints** | Função pública sem tipos (Python sem annotations) | BAIXO-MÉDIO |
| **Testes frágeis** | Teste depende de ordem, estado global, ou tempo | MÉDIO |
| **Migrations divergentes** | Alembic com múltiplas heads / Django com conflitos | ALTO |

### Evidência mínima

- "`apps/api/` tem 47 ocorrências de `: Any` (rg) — top 5: `models.py:12`, `produtos.py:45`..."
- "Bloco de 15 linhas idêntico em `produtos_service.py:89` e `estoque.py:134`"

---

## 6. Arquitetura / Dívida Estrutural

### O que procurar

| Problema | Como detectar | Severidade típica |
|----------|--------------|-------------------|
| **`if tipo == x` espalhado** | Grep por `if.*tipo_.*==` / `if.*kind.*==` em vez de registry/strategy | ALTO |
| **Lógica de negócio no router** | Router com >20 linhas de lógica (deveria estar em service) | MÉDIO |
| **Lógica de negócio no componente** | Componente React com cálculos/transformações que deveriam estar em hook/util | MÉDIO |
| **God object** | Classe/módulo com >10 métodos públicos / >500 linhas | ALTO |
| **Camadas misturadas** | Service faz query SQL direta + monta response HTTP | ALTO |
| **Violação de contrato** | Service retorna dict quando schema espera Pydantic model | MÉDIO |
| **Falta de abstração** | 3 endpoints com 80% de código idêntico, sem helper comum | MÉDIO |
| **Dependência de impl** | Código depende de impl interna de lib (ex: acessar `._field` de Pydantic) | ALTO |
| **Estado implícito** | Função cujo resultado depende de variável global não passada como param | ALTO |
| **Feature flag permanente** | Flag que existe há meses e nunca foi removida | BAIXO |

### Evidência mínima

- "`apps/api/routers/checkout.py:34–89` — 55 linhas de lógica de negócio no router (validação + cálculo + chamada pagamento). Service `checkout.py` existe mas não é usado aqui."
- "`rg 'if.*tipo_pedido.*==' apps/api/` retorna 8 ocorrências em 5 arquivos — deveria usar registry"

### O que NÃO é achado de arquitetura

- "Deveria usar Clean Architecture" (opinião de framework, não achado concreto)
- "Monolito ruim" (sem evidência de dor causada pelo monolito)
- "Falta DDD" (buzzword sem problema concreto)

---

## Tabela de severidade (referência)

| Severidade | Critério | Ação |
|-----------|---------|------|
| **CRÍTICO** | Causa bug em produção, perda de dados, crash, ou degradação grave (>2s) com crescimento | Corrigir antes de deploy |
| **ALTO** | Impacto real em UX/performance/manutenção, mas não crash. Piora com escala. | Corrigir na sprint corrente |
| **MÉDIO** | Dívida acumulável. Não dói hoje, dói em 3 meses. | Planejar correção |
| **BAIXO** | Melhoria incremental. Não causa problema real. | Nice to have |
| **INFO** | Observação. Bom saber. | Não precisa de ação |

---

## Resumo de prioridade de eixos

| Prioridade | Eixo | Por quê |
|-----------|------|---------|
| 1 | Performance backend (N+1, paginação, cache) | Impacto direto no usuário, mensurável |
| 2 | Performance frontend (bundle, re-renders) | Impacto direto no usuário, mensurável |
| 3 | Escalabilidade (jobs, pools, locks) | Bomba-relógio com crescimento |
| 4 | Arquitetura (camadas, God object, registry) | Dívida que freia features novas |
| 5 | Manutenibilidade (morto, duplicação, any) | Dívida acumulativa |
| 6 | Legibilidade (complexidade, nomes, magic) | Importante mas menor impacto direto |
