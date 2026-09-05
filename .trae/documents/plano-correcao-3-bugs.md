# Plano: Correção de 3 Bugs na Análise de Currículos

## Resumo
Corrigir três problemas na análise de currículos:
1. LLM flagga certificações de cursos online (HTML5, CSS3, etc.) como "não são certificações reais"
2. LLM considera datas de 2026 como "ano no futuro" (hoje é setembro/2026)
3. LLM ancora erros de capitalização que não são removidos pelo pós-processamento

---

## Análise do Estado Atual

### Problema 1 — Certificações
- **Local**: `knowledge/cv_analysis_prompt.md`
- **Causa**: O prompt não tem regra específica sobre certificações. A LLM interpreta "certificações reais emitidas por instituições" de forma restritiva, excluindo certificações de cursos online (freeCodeCamp, Udemy, Coursera, etc.)
- **Onde aparece**: No campo `erros_comuns_detectados` do JSON de resposta da LLM

### Problema 2 — Datas (ano 2026)
- **Local**: `knowledge/cv_analysis_prompt.md`
- **Causa**: A LLM não sabe que o ano atual é 2026. Ela assume implicitamente que 2024/2025 é o ano corrente e marca datas de 2026 como "futuras/incoerentes"
- **Onde aparece**: No campo `erros_comuns_detectados` com mensagem tipo "Data de formação parece incorreta (ano no futuro)"

### Problema 3 — Capitalização
- **Local**: `backend/main.py` (pós-processamento) + `knowledge/cv_analysis_prompt.md`
- **Causa**: O pós-processamento já filtra erros de capitalização em `erros_ortograficos` (linhas 1178-1182) e em `erros_comuns_detectados` (linhas 1272-1281), MAS a filtragem em `erros_comuns_detectados` só remove se o **tipo** ou a **descrição** contiverem palavras-chave como "capitaliz", "maiúscula", "uppercase". Se a LLM gera um erro com tipo diferente (ex: "formatacao_inconsistente") mas a descrição fala de maiúsculas, não é capturada.
- **Onde aparece**: No campo `erros_comuns_detectados`

---

## Mudanças Propostas

### Arquivo 1: `knowledge/cv_analysis_prompt.md`

#### Mudança 1A — Adicionar ano atual no topo (para problema de datas)
Na seção de REGRAS CRÍTICAS, após a regra 5, adicionar:

```
5.5 **ANO ATUAL: 2026.** Datas em 2024, 2025 e 2026 são todas válidas e normais.
   NUNCA marque datas de 2024-2026 como "ano no futuro" ou "incorretas".
   "Fev. De 2026 – Presente" é perfeitamente válido (indica que a pessoa está cursando/trabalhando atualmente).
```

#### Mudança 1B — Adicionar regra sobre certificações (para problema de certificações)
Na seção "6. SEÇÕES OPCIONAIS", substituir a linha sobre certificações:

De:
```
- **Certificações**: Se relevantes, incluir.
```

Para:
```
- **Certificações**: Se relevantes, incluir.
  **NUNCA flagge certificações como "não reais" ou "só tecnologias".**
  Certificações de cursos online (freeCodeCamp, Udemy, Coursera, Alura, etc.) SÃO certificações válidas.
  Certificações de tecnologias (HTML5, CSS3, JavaScript, SQL, etc.) SÃO certificações válidas.
  NÃO discrimine entre nível da certificação (Harvard vs. curso online) — certificado é certificado.
  O único critério é: o candidato declarou ter obtido uma certificação? Se sim, é válido.
```

#### Mudança 1C — Reforçar regra de capitalização (para problema de capitalização)
Na seção "5. CAPITALIZAÇÃO", adicionar após os exemplos:

```
- **REGRAS DE EXCLUSÃO ABSOLUTA:**
  * SE uma palavra está em MAIÚSCULAS e está ORTOGRAFICAMENTE CORRETA → NUNCA flagge.
  * SE a "correção" sugerida é apenas a versão em lowercase da palavra → NUNCA flagge (é capitalização, não erro).
  * Ex: "HTML5" → NÃO flaggear (correto em caps). "CSS3" → NÃO flaggear. "JAVASCRIPT" → NÃO flaggear.
  * Em `erros_comuns_detectados`: NUNCA crie erros do tipo "capitalização" ou que mencionem maiúsculas/minúsculas.
```

### Arquivo 2: `backend/main.py`

#### Mudança 2A — Fortalecer filtragem de capitalização em `erros_comuns_detectados`
Na seção de pós-processamento (linha ~1272), expandir a filtragem para também verificar se a **palavra** ou a **correção** indicam capitalização:

```python
# Verificar se o erro é sobre capitalização (palavra + correção = mesma palavra em cases diferentes)
if (correcao and word.lower() == correcao.lower() and word != correcao):
    continue  # É apenas capitalização diferente, não erro
# Verificar se exemplo é toda maiúscula e a descrição não aponta erro real
if exemplo and exemplo == exemplo.upper() and len(exemplo) > 1:
    # Verificar se a versão lowercase existe no texto → é capitalização
    if _norm(exemplo.lower()) in _words_norm:
        continue
```

---

## Arquivos Alterados

| Arquivo | Tipo de Mudança | Linhas Aproximadas |
|---------|----------------|-------------------|
| `knowledge/cv_analysis_prompt.md` | Adicionar regra 5.5 + melhorar seção 6 + reforçar seção 5 | ~17, ~231, ~82 |
| `backend/main.py` | Expandir filtragem de capitalização em erros_comuns_detectados | ~1272-1281 |

---

## Passo a Passo

1. **Editar `knowledge/cv_analysis_prompt.md`**:
   - Adicionar regra 5.5 (ano atual 2026) após a regra 5
   - Substituir regra de certificações (linha ~231) pela versão expandida
   - Adicionar regras de exclusão absoluta na seção 5 (linha ~82)

2. **Editar `backend/main.py`**:
   - Adicionar verificação de capitalização por comparação word.lower() == correcao.lower() na filtragem de `erros_comuns_detectados`

3. **Testar**:
   - Executar análise de PDF com certificações de tecnologia (HTML5, CSS3)
   - Executar análise de PDF com data "Fev. De 2026 – Presente"
   - Executar análise de PDF com palavras em maiúsculas
   - Verificar que nenhum dos três erros aparece mais

---

## Suposições
- O backend já está rodando com `--reload` (Hot reload do uvicorn)
- O frontend não precisa de alterações (os erros vêm da LLM, não da UI)
- As mudanças são apenas no prompt e no pós-processamento, não na estrutura de dados

---

## Verificação
- [ ] Certificações HTML5/CSS3/JS não mais flaggadas como "não reais"
- [ ] Data "Fev. De 2026 – Presente" não mais flaggada como "ano no futuro"
- [ ] Palavras em maiúsculas não mais gerando erros de capitalização
- [ ] TypeScript compila sem erros
- [ ] Backend retorna status 200 em todos os testes
