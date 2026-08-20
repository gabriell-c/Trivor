/**
 * Trivor — LinkedIn Profile Exporter
 * Content Script v3.6 — Extração SEM navegar para /details/
 *
 * Estratégia: extrair TUDO da página principal do perfil,
 * clicando em "Exibir todos" e fazendo scroll para carregar conteúdo lazy.
 */
"use strict";

const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const clean = (s = "") => (s || "").replace(/\s+/g, " ").trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const SKIP_KEYWORDS = [
  "editar",
  "edit",
  "añadir",
  "add",
  "criar",
  "criar novo",
  "seguir",
  "follow",
  "conectar",
  "connect",
  "curtir",
  "like",
  "enviar",
  "send",
  "salvar",
  "save",
  "agendar",
  "schedule",
  "configurar",
  "settings",
  "gerenciar",
  "manage",
  "publicar",
  "publish",
  "descartar",
  "discard",
  "cancelar",
  "cancel",
  "remover",
  "remove",
];

function detectLang() {
  const l = (document.documentElement.lang || "").toLowerCase();
  if (l.startsWith("pt")) return "pt";
  if (l.startsWith("es")) return "es";
  return "en";
}

function getNodeText(node) {
  if (!node) return "";
  const c = node.cloneNode(true);
  $$("script,style,noscript,svg,img,button,a,link,meta,iframe", c).forEach(
    (e) => e.remove(),
  );
  return clean(c.innerText || c.textContent || "");
}

// =========================================================================
// 1. Expandir botões "…mais" / "ler mais" (seguro)
// =========================================================================
async function expandAllTextButtons() {
  const EXPAND = [
    "… mais",
    "…mais",
    "ler mais",
    "read more",
    "leer más",
    "ver mais",
    "show more",
    "mostrar mais",
    "mostrar más",
    "ver tudo",
    "see all",
    "view all",
    "show all",
  ];

  if (/\/edit\//i.test(location.href)) return 0;
  let clicked = 0;
  for (let round = 0; round < 10; round++) {
    let found = false;
    $$("button", document)
      .filter((b) => {
        if (b.disabled || b.offsetParent === null) return false;
        if (b.closest('[data-testid="dialog"]') !== null) return false;
        if (b.closest("form") !== null) return false;
        const text = clean(b.innerText || "").toLowerCase();
        return (
          EXPAND.some(
            (kw) =>
              text === kw.toLowerCase() ||
              text.endsWith(" " + kw.toLowerCase()) ||
              text.includes("…" + kw.toLowerCase()),
          ) &&
          !SKIP_KEYWORDS.some((kw) => text.includes(kw) && text.length < 40)
        );
      })
      .forEach((b) => {
        try {
          b.click();
          clicked++;
          found = true;
        } catch {}
      });

    $$('[aria-expanded="false"]', document).forEach((el) => {
      if (el.closest('[data-testid="dialog"]') !== null) return;
      if (el.closest("form") !== null) return;
      const label = (el.getAttribute("aria-label") || "").toLowerCase();
      if (
        /(mais|more|expand|all|todos|ver tudo)/i.test(label) &&
        !SKIP_KEYWORDS.some((kw) => label.includes(kw))
      ) {
        try {
          el.click();
          clicked++;
          found = true;
        } catch {}
      }
    });
    if (!found && round > 3) break;
    await sleep(80);
  }
  await sleep(200);
  return clicked;
}

// =========================================================================
// 2. Clicar em "Exibir todos os X itens" / "Exibir tudo"
// =========================================================================
async function clickShowAll() {
  let clicked = 0;
  // Padrões comuns do LinkedIn
  const patterns = [
    /exibir todos os?\s*\d+\s*itens?/i,
    /exibir todos os?/i,
    /exibir as?\s*\d+/i,
    /ver todos os?\s*\d+/i,
    /view all/i,
    /show all/i,
    /exibir tudo/i,
    /ver tudo/i,
  ];
  const candidates = $$('button, a, span[role="button"]', document).filter(
    (el) => {
      if (el.disabled || el.offsetParent === null) return false;
      if (el.closest('[data-testid="dialog"]') !== null) return false;
      const text = clean(
        el.innerText || el.getAttribute("aria-label") || "",
      ).toLowerCase();
      return patterns.some((p) => p.test(text)) && text.length < 100;
    },
  );
  for (const el of candidates) {
    try {
      el.click();
      clicked++;
      await sleep(600);
    } catch {}
  }
  return clicked;
}

// =========================================================================
// 3. Scroll para carregar conteúdo lazy
// =========================================================================
async function scrollToLoad(maxScrolls = 15) {
  for (let i = 0; i < maxScrolls; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(400);
    // Para se não houver mais conteúdo para carregar
    if (document.documentElement.scrollHeight <= window.innerHeight + 2000)
      break;
  }
  window.scrollTo(0, 0);
  await sleep(300);
}

// =========================================================================
// 4. Aguardar elemento aparecer
// =========================================================================
function waitForSelector(sel, timeout = 10000) {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = () => {
      if ($(sel)) {
        resolve(true);
        return;
      }
      if (Date.now() - start > timeout) {
        resolve(false);
        return;
      }
      setTimeout(check, 300);
    };
    check();
  });
}

// =========================================================================
// 5. Extrair cards de uma seção
// =========================================================================
function extractSectionCards() {
  const items = [];
  // LinkedIn usa [data-view-name] ou [class*="artdeco-card"] ou [class*="card"]
  const selectors = [
    '[data-testid="experience-card"]',
    '[data-testid="education-card"]',
    '[data-testid="certification-card"]',
    '[data-testid="project-card"]',
    '[data-testid="skill-card"]',
    '[data-testid="course-card"]',
    '[data-testid="language-card"]',
    '[class*="card"]',
    '[class*="artifact"]',
    '[class*="base-list"] li',
    'li[class*="card"]',
  ];

  for (const sel of selectors) {
    const found = $$(sel, document);
    if (found.length > 0) {
      for (const card of found) {
        const text = getNodeText(card);
        if (
          text.length > 20 &&
          text.length < 2000 &&
          !/exibir|ver todos|ler mais|mostrar mais|ver tudo/i.test(text)
        ) {
          items.push(text);
        }
      }
      break; // encontrou estrutura válida
    }
  }

  // Fallback: busca por qualquer bloco com 2+ linhas
  if (items.length === 0) {
    const allBlocks = $$(
      'div[class*="base"], div[class*="card"], div[class*="item"], section',
    );
    for (const block of allBlocks) {
      const text = getNodeText(block);
      const lines = text.split("\n").filter((l) => clean(l).length > 2);
      if (
        lines.length >= 2 &&
        text.length > 30 &&
        text.length < 1500 &&
        !/exibir|ver todos|ler mais|mostrar mais/i.test(text)
      ) {
        items.push(text);
      }
    }
  }

  return items;
}

// =========================================================================
// 6. Extrair seção "Sobre"
// =========================================================================
function extractAbout() {
  const el = $$("span").find((s) => {
    const text = clean(s.innerText || "").toLowerCase();
    return text.startsWith("sobre") || text.startsWith("about");
  });
  if (!el) return "";
  const sec = el.closest("section") || el.parentElement;
  if (!sec) return "";
  // Pega o texto após o heading "Sobre"
  let found = false;
  let result = "";
  const walker = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT, null);
  let node;
  while ((node = walker.nextNode())) {
    const t = clean(node.textContent);
    if (!found) {
      if (
        t.toLowerCase().includes("sobre") ||
        t.toLowerCase().includes("about")
      )
        found = true;
      continue;
    }
    if (t.length > 3 && result.length < 3000) result += t + " ";
  }
  return clean(result);
}

// =========================================================================
// 7. Extrair experiências da página principal
// =========================================================================
function extractExperiences() {
  const items = [];
  const cards = $$('[data-testid="experience-card"], [class*="experience"]');
  if (cards.length === 0) {
    // Fallback
    const sections = $$("section");
    for (const sec of sections) {
      const text = getNodeText(sec);
      if (
        text.includes("Empresa") ||
        text.includes("Cargo") ||
        /\d{4}/.test(text)
      ) {
        const lines = text.split("\n").filter((l) => clean(l).length > 3);
        if (lines.length >= 2) items.push(text);
      }
    }
  } else {
    for (const card of cards) {
      const text = getNodeText(card);
      if (
        text.length > 20 &&
        text.length < 2000 &&
        !/exibir|ver mais|ler mais/i.test(text)
      ) {
        items.push(text);
      }
    }
  }
  return items;
}

// =========================================================================
// 8. Extrair atividades (sem navegar — apenas texto visível na home)
// =========================================================================
function extractActivities() {
  const items = [];
  // Procura a seção "Atividade recente" no perfil
  const actSec = $$('section, [class*="section"]').find((sec) => {
    const t = getNodeText(sec).toLowerCase();
    return t.includes("atividade recente") || t.includes("recent activity");
  });
  if (actSec) {
    const cards = $$('li, [class*="card"], [class*="artifact"]', actSec);
    for (const card of cards) {
      const text = getNodeText(card);
      if (
        text.length > 20 &&
        text.length < 1500 &&
        !/exibir|ver mais|ler mais|mostrar mais/i.test(text)
      ) {
        items.push(text);
      }
    }
  }
  return items;
}

// =========================================================================
// 9. Extração principal — TUDO em uma página só
// =========================================================================
async function extractMainPage() {
  const lang = detectLang();

  // Coleta dados do topo
  const nameEl = $("h1, .text-heading-xlarge", document);
  const headlineEl = $(".text-body-medium.break-words", document);
  const locEl = $(".text-body-small.inline.t-black--light", document);

  // Expande botões "...mais" na página (NUNCA clica "Exibir todos" globalmente — isso navega para outras páginas)
  const expansions = await expandAllTextButtons();
  await scrollToLoad(10);
  await sleep(800);

  // Segunda passada de expansão após scroll
  const expansions2 = await expandAllTextButtons();
  await scrollToLoad(5);
  await sleep(500);

  const data = {
    nome: nameEl ? clean(nameEl.innerText) : "",
    headline: headlineEl ? clean(headlineEl.innerText) : "",
    localizacao: locEl ? clean(locEl.innerText) : "",
    sobre: extractAbout(),
    experiencias: extractExperiences(),
    atividades: extractActivities(),
    expansoes: expansions + expansions2,
  };

  // Modal de preferências de emprego
  const detailsBtn = $$("a, button").find((el) => {
    if (el.closest('[data-testid="dialog"]') !== null) return false;
    const t = clean(el.innerText || "").toLowerCase();
    return t === "exibir detalhes" || t === "view details";
  });
  if (detailsBtn) {
    try {
      detailsBtn.click();
      await sleep(1000);
      const dialog = $('dialog[open], [role="dialog"]', document);
      if (dialog) {
        data.preferencias_emprego = getNodeText(dialog);
        const closeBtn = $(
          'button[aria-label="Fechar"], button[aria-label="Close"]',
          dialog,
        );
        if (closeBtn) {
          closeBtn.click();
          await sleep(500);
        } else {
          document.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
          );
          await sleep(300);
        }
      }
    } catch {}
  }

  // Agora extrai cada seção clicando em "Exibir todos" e scrollando
  // Seção: Formação Acadêmica
  data.educacao = await extractSectionWithExpand(
    "formação acadêmica",
    "education",
  );
  // Seção: Licenças e Certificações
  data.certificacoes = await extractSectionWithExpand(
    "certificações",
    "certification",
  );
  // Seção: Projetos
  data.projetos = await extractSectionWithExpand("projetos", "project");
  // Seção: Habilidades
  data.habilidades = await extractSectionWithExpand("competências", "skill");
  // Seção: Cursos
  data.cursos = await extractSectionWithExpand("cursos", "course");
  // Seção: Idiomas
  data.idiomas = await extractSectionWithExpand("idiomas", "language");

  return data;
}

/**
 * Encontra uma seção pelo título, clica "Exibir todos", scrolla e extrai
 */
async function extractSectionWithExpand(titleKeyword, dataTestId) {
  // 1. Encontra o botão "Exibir todos" desta seção
  const sections = $$('section, [class*="section"]');
  let targetSection = null;
  let showAllBtn = null;

  for (const sec of sections) {
    const text = getNodeText(sec);
    if (
      text.includes(titleKeyword) ||
      text.toLowerCase().includes(titleKeyword)
    ) {
      targetSection = sec;
      // Procura botão "Exibir todos" dentro da seção
      showAllBtn = sec.querySelector("button, a");
      break;
    }
  }

  if (!targetSection) {
    // Tenta buscar pelo data-testid
    targetSection = $(
      `[data-testid*="${dataTestId}-section"], [data-section="${dataTestId}"]`,
    );
  }

  if (!targetSection) return [];

  // 2. Clica em "Exibir todos" se existir
  const showAllPatterns = [
    /exibir todos os?\s*\d+/i,
    /exibir todos/i,
    /ver todos os?\s*\d+/i,
    /exibir tudo/i,
    /view all/i,
  ];
  const allBtns = $$("button, a", targetSection);
  for (const btn of allBtns) {
    const text = clean(
      btn.innerText || btn.getAttribute("aria-label") || "",
    ).toLowerCase();
    if (showAllPatterns.some((p) => p.test(text))) {
      // Não clica links que navigam para fora do perfil
      const href = (btn.getAttribute("href") || "").toLowerCase();
      if (
        href &&
        (href.includes("/recent-activity/") || href.includes("/edit/"))
      )
        continue;
      try {
        btn.click();
        await sleep(1000);
        break;
      } catch {}
    }
  }

  // 3. Scroll para carregar conteúdo
  await scrollToLoad(10);
  await waitForSelector('[data-testid*="card"], [class*="card"]', 8000);
  await sleep(1000);

  // 4. Extrai os cards da seção
  const cards = $$(
    `[data-testid*="${dataTestId}-card"], ` +
      `[data-testid*="experience-card"], ` +
      `[data-testid*="education-card"], ` +
      `[data-testid*="certification-card"], ` +
      `[data-testid*="project-card"], ` +
      `[data-testid*="skill-card"], ` +
      `[data-testid*="course-card"], ` +
      `[data-testid*="language-card"], ` +
      `[class*="card"], ` +
      `[class*="artifact"]`,
  );

  const items = [];
  for (const card of cards) {
    const text = getNodeText(card);
    if (
      text.length > 20 &&
      text.length < 2000 &&
      !/exibir|ver todos|ler mais|mostrar mais/i.test(text)
    ) {
      items.push(text);
    }
  }

  return items;
}

// =========================================================================
// 10. Handler principal
// =========================================================================
async function extractCurrentStep(step) {
  if (/\/edit\//i.test(location.href)) {
    return { success: false, error: "Página de edição detectada." };
  }

  try {
    if (step === "MAIN") {
      const data = await extractMainPage();
      return { success: true, data };
    }

    // Etapas posteriores não são mais necessárias — tudo é extraído na MAIN
    return { success: true, data: {} };
  } catch (err) {
    return { success: false, error: err.message || String(err) };
  }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "EXTRACT_STEP") {
    // Proteção: se a URL mudou para fora do perfil, aborta
    const currentUrl = location.href;
    if (
      /\/recent-activity\//i.test(currentUrl) ||
      /\/edit\//i.test(currentUrl)
    ) {
      sendResponse({
        success: false,
        error: "URL inesperada detectada: " + currentUrl,
      });
      return false;
    }
    extractCurrentStep(request.step)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
