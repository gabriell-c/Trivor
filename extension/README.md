# 🔌 Trivor — Extension: LinkedIn Profile Exporter

> Extensão oficial para Google Chrome / Microsoft Edge projetada para exportar 100% dos dados do **próprio perfil autenticado no LinkedIn** em formato **JSON** ou **Markdown (.md)** de alta qualidade para análise avançada por inteligência artificial (ChatGPT, Claude, Trivor SaaS, etc.).

---

## 🎯 Objetivos e Princípios Éticos

1. **Privacidade Total**: A extensão opera 100% no navegador do usuário, utilizando a sessão ativa. Nenhum dado é enviado a servidores externos.
2. **Uso Pessoal**: Destinada **exclusivamente** à exportação do perfil próprio do usuário logado.
3. **Sem Automata / Scraping Massivo**: Não utiliza Selenium, Puppeteer nem executa requisições automatizadas em lote de perfis de terceiros.
4. **Acionamento Manual**: O processo inicia apenas sob clique do usuário no botão "Exportar Meu Perfil".

---

## 🛠️ Funcionalidades Principal

- ⚡ **Expansão Automática de Seções**: Clica autonomamente em botões recolhidos ("Ver mais", "Mostrar tudo", "Expandir") para garantir a captura do conteúdo completo antes da extração.
- 🌍 **Suporte Multi-Idioma (PT / EN / ES)**: Dicionários inteligentes de localização para identificar seções em perfis em Português, Inglês ou Espanhol.
- 🧩 **Resiliência Estrutural**: Não depende exclusivamente de classes CSS frágeis do LinkedIn (que mudam frequentemente). Utiliza headings semânticos, atributos `aria-label` e seletores estáveis.
- 💾 **Exportação Dual (JSON e Markdown)**:
  - **JSON**: Estrutura de dados limpa e tipada para ingestão em APIs e prompts de IA.
  - **Markdown (.md)**: Formato ideal para leitura humana e colagem direta em LLMs (ChatGPT, Claude, Gemini).

---

## 📁 Estrutura do Projeto

```
extension/
├── manifest.json            # Configuração Manifest V3 (Chrome/Edge)
├── generate_icons.py        # Gerador de ícones PNG
├── icons/                   # Ícones da extensão (16, 32, 48, 128px)
│   ├── icon16.png
│   ├── icon32.png
│   ├── icon48.png
│   └── icon128.png
└── src/
    ├── background.js        # Service worker (Manifest V3)
    ├── content.js           # Content Script (Injetado na página do LinkedIn)
    ├── popup.html           # Interface do Usuário (Glassmorphism Dark)
    ├── popup.js             # Lógica da UI, download e cópia de arquivos
    └── lib/
        └── extractor.js     # Extrator core multi-idioma
```

---

## 🚀 Como Instalar no Google Chrome / Microsoft Edge

1. Abra o navegador e acesse a página de extensões:
   - **Chrome**: `chrome://extensions/`
   - **Edge**: `edge://extensions/`
2. No canto superior direito, ative o **"Modo do desenvolvedor"** (Developer mode).
3. Clique em **"Carregar sem compactação"** (Load unpacked).
4. Selecione a pasta `extension` deste repositório (`python/curriculo/extension`).
5. A extensão **Trivor Exporter** aparecerá instalada e pronta para uso no menu da barra de ferramentas!

---

## 📑 Passo a Passo de Uso

1. Abra o **LinkedIn** (`https://www.linkedin.com/in/seu-perfil`) no seu perfil pessoal.
2. Clique no ícone da extensão **Trivor Exporter** no canto superior direito do navegador.
3. Clique no botão **⚡ Exportar Meu Perfil**.
4. A extensão irá expandir automaticamente as seções ocultas do seu perfil e coletar os dados em poucos segundos.
5. Escolha entre:
   - 📋 **Copiar JSON**: Para colar direto no ChatGPT / Claude.
   - 💾 **Baixar JSON**: Salvar como arquivo `.json`.
   - 📝 **Baixar Markdown**: Salvar como arquivo `.md` estruturado em cabeçalhos.

---

## 🧠 Exemplo de Dados Capturados no JSON

```json
{
  "fonte": "trivor_linkedin_exporter",
  "versao": "1.0.0",
  "url": "https://www.linkedin.com/in/usuario",
  "idioma_detectado": "pt",
  "extraido_em": "2026-08-16T17:15:00.000Z",
  "dados": {
    "nome": "Seu Nome Completo",
    "headline": "Engenheiro de Software | Full Stack | Python | Next.js",
    "localizacao": "São Paulo, SP",
    "about": "Desenvolvedor com experiência em...",
    "experience": "Empresa X • Cargo Y...",
    "experiencias_detalhadas": [
      {
        "texto_bruto": "Desenvolvedor Senior na Empresa X (2023 - Presente)..."
      }
    ],
    "education": "Universidade Y • Engenharia de Software...",
    "certifications": "AWS Certified Developer...",
    "skills": "Python, React, TypeScript, FastApi..."
  }
}
```

---

## 📄 Licença

Desenvolvido para o projeto **Trivor** — Todos os direitos reservados.