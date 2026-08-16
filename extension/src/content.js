/**
 * Trivor — LinkedIn Profile Exporter
 * Content Script (Injetado nas abas do LinkedIn)
 */

'use strict';

// ---------------------------------------------------------------------------
// 1. Script de Extração embutido no contexto da página
// ---------------------------------------------------------------------------

function runExtraction() {
  const SECTIONS = [
    { key: 'contact', labels: { pt: ['informações de contato', 'contato'], en: ['contact info', 'contact'], es: ['información de contacto', 'contacto'] } },
    { key: 'about', labels: { pt: ['sobre', 'resumo', 'about'], en: ['about'], es: ['acerca de', 'sobre', 'resumen'] } },
    { key: 'experience', labels: { pt: ['experiências', 'experiência'], en: ['experience'], es: ['experiencia', 'experiencias'] } },
    { key: 'education', labels: { pt: ['formação acadêmica', 'formação', 'educação'], en: ['education'], es: ['formación', 'educación'] } },
    { key: 'certifications', labels: { pt: ['licenças e certificações', 'certificações', 'licenças'], en: ['licenses and certifications', 'certifications', 'licenses'], es: ['licencias y certificaciones', 'certificaciones'] } },
    { key: 'projects', labels: { pt: ['projetos'], en: ['projects'], es: ['proyectos'] } },
    { key: 'courses', labels: { pt: ['cursos'], en: ['courses'], es: ['cursos'] } },
    { key: 'skills', labels: { pt: ['competências e soft skills', 'competências', 'habilidades'], en: ['skills', 'competencies'], es: ['aptitudes', 'competencias'] } },
    { key: 'languages', labels: { pt: ['idiomas'], en: ['languages'], es: ['idiomas'] } },
    { key: 'interests', labels: { pt: ['interesses'], en: ['interests'], es: ['intereses'] } },
    { key: 'volunteer', labels: { pt: ['voluntariado', 'trabalho voluntário'], en: ['volunteer experience', 'volunteering'], es: ['voluntariado', 'experiencia de voluntariado'] } },
    { key: 'publications', labels: { pt: ['publicações'], en: ['publications'], es: ['publicaciones'] } },
    { key: 'recommendations', labels: { pt: ['recomendações'], en: ['recommendations'], es: ['recomendaciones'] } },
    { key: 'honors', labels: { pt: ['prêmios e honrarias', 'honrarias', 'prêmios'], en: ['honors and awards', 'honors', 'awards'], es: ['premios y honores', 'premios'] } },
    { key: 'organizations', labels: { pt: ['organizações'], en: ['organizations'], es: ['organizaciones'] } },
    { key: 'featured', labels: { pt: ['destaques'], en: ['featured'], es: ['destacados'] } },
    { key: 'activity', labels: { pt: ['atividade recente', 'atividade'], en: ['activity'], es: ['actividad'] } }
  ];

  const EXPAND_LABELS = {
    pt: ['mostrar mais', 'ver todos', 'ver tudo', 'ver mais', 'expandir', 'mostrar tudo'],
    en: ['show more', 'see all', 'view all', 'show all', 'expand', 'more'],
    es: ['mostrar más', 'ver todo', 'ver todos', 'ampliar', 'expandir', 'más']
  };

  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
  const cleanText = (s = '') => (s || '').replace(/\s+/g, ' ').trim();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function detectLang() {
    const l = (document.documentElement.lang || '').toLowerCase();
    if (l.startsWith('pt')) return 'pt';
    if (l.startsWith('es')) return 'es';
    if (l.startsWith('en')) return 'en';
    const body = (document.body && document.body.innerText || '').slice(0, 3000).toLowerCase();
    if (/\b(sobre|formação|experiência|idiomas|competências)\b/.test(body)) return 'pt';
    if (/\b(acerca de|formación|experiencia|aptitudes)\b/.test(body)) return 'es';
    return 'en';
  }

  function getNodeText(node) {
    if (!node) return '';
    const clone = node.cloneNode(true);
    $$( 'script,style,noscript,svg', clone).forEach((el) => el.remove());
    return cleanText(clone.innerText || clone.textContent || '');
  }

  async function expandAll() {
    const lang = detectLang();
    const labels = EXPAND_LABELS[lang] || EXPAND_LABELS.en;
    let clicked = 0;
    for (let round = 0; round < 10; round++) {
      let found = false;
      const btns = $$('button', document).filter((b) => {
        if (b.disabled) return false;
        const t = cleanText(b.innerText || '').toLowerCase();
        return labels.some((lab) => t === lab || t.includes(lab));
      });
      for (const b of btns) {
        try { b.click(); clicked++; found = true; await sleep(80); } catch {}
      }
      const collapsed = $$('[aria-expanded="false"]', document);
      for (const el of collapsed) {
        const r = el.getAttribute('role') || '';
        const l = (el.getAttribute('aria-label') || '').toLowerCase();
        if (r === 'button' && /(mais|all|more|todos|expand)/.test(l)) {
          try { el.click(); clicked++; found = true; await sleep(80); } catch {}
        }
      }
      if (!found || clicked > 50) break;
    }
    await sleep(400);
    return clicked;
  }

  function findSection(key) {
    const lang = detectLang();
    const def = SECTIONS.find((s) => s.key === key);
    if (!def) return null;
    const labels = def.labels[lang] || def.labels.en;
    const candidates = $$('section, div[id], h2, h3, span[aria-label]', document);
    for (const el of candidates) {
      const t = cleanText(el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
      if (!t || t.length > 250) continue;
      if (labels.some((lab) => t === lab || t.startsWith(lab) || t.includes(lab))) {
        return el.closest('section') || el.closest('div') || el;
      }
    }
    return null;
  }

  function parseExperiences(sec) {
    const out = [];
    const lis = $$('li', sec).slice(0, 30);
    for (const li of lis) {
      const text = getNodeText(li);
      if (text.length > 3) out.push({ texto_bruto: text });
    }
    if (out.length === 0) {
      const full = getNodeText(sec);
      if (full) out.push({ texto_bruto: full });
    }
    return out;
  }

  return (async () => {
    const expandCount = await expandAll();
    const lang = detectLang();

    const profile = {
      fonte: 'trivor_linkedin_exporter',
      versao: '1.0.0',
      url: location.href,
      idioma_detectado: lang,
      expansoes_realizadas: expandCount,
      extraido_em: new Date().toISOString(),
      dados: {}
    };

    const nameEl = document.querySelector('h1, .text-heading-xlarge');
    profile.dados.nome = nameEl ? cleanText(nameEl.innerText) : '';

    const headlineEl = document.querySelector('.text-body-medium.break-words');
    profile.dados.headline = headlineEl ? cleanText(headlineEl.innerText) : '';

    const locEl = document.querySelector('.text-body-small.inline.t-black--light');
    profile.dados.localizacao = locEl ? cleanText(locEl.innerText) : '';

    for (const def of SECTIONS) {
      const secNode = findSection(def.key);
      profile.dados[def.key] = secNode ? getNodeText(secNode) : '';
    }

    const expNode = findSection('experience');
    profile.dados.experiencias_detalhadas = expNode ? parseExperiences(expNode) : [];

    return profile;
  })();
}

// Escuta mensagens do popup/background
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'EXTRACT_PROFILE') {
    runExtraction()
      .then((profileData) => {
        sendResponse({ success: true, data: profileData });
      })
      .catch((err) => {
        sendResponse({ success: false, error: err.message || String(err) });
      });
    return true; // async
  }
});