/**
 * Trivor — LinkedIn Profile Exporter
 * Popup Logic — Extração em UMA página (sem navegar para /details/)
 */
'use strict';

document.addEventListener('DOMContentLoaded', async () => {
  const btnExtract = document.getElementById('btnExtract');
  const btnStop = document.getElementById('btnStop');
  const btnCopy = document.getElementById('btnCopy');
  const btnDownloadJson = document.getElementById('btnDownloadJson');
  const btnDownloadMd = document.getElementById('btnDownloadMd');
  const statusText = document.getElementById('statusText');
  const jsonOutput = document.getElementById('jsonOutput');
  const resultBox = document.getElementById('resultBox');
  const toast = document.getElementById('toast');

  let extractedData = null;
  let isRunning = false;
  let shouldStop = false;

  function showToast(msg, type = 'success') {
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    setTimeout(() => { toast.className = 'toast'; }, 4000);
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab || !tab.url || !tab.url.includes('linkedin.com')) {
    statusText.innerHTML = '⚠️ Abra uma aba do <strong>LinkedIn</strong> e tente novamente.';
    btnExtract.disabled = true;
    return;
  }

  statusText.innerHTML = '✅ LinkedIn detectado! Clique em <strong>Exportar Meu Perfil Completo</strong>.';

  let accumulated = {};

  function sendAndWait(tabId, msg, timeout = 120000) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        resolve({ success: false, error: `Timeout (${timeout / 1000}s)` });
      }, timeout);
      chrome.tabs.sendMessage(tabId, msg, (response) => {
        clearTimeout(timer);
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(response || { success: false, error: 'Resposta vazia' });
        }
      });
    });
  }

  async function injectScript(tabId) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['src/content.js']
      });
    } catch {}
    await new Promise(r => setTimeout(r, 300));
  }

  function stopExtraction() {
    shouldStop = true;
    isRunning = false;
    btnExtract.disabled = false;
    btnStop.disabled = true;
    btnExtract.innerHTML = '⚡ Exportar Meu Perfil Completo';
    statusText.innerHTML = '❌ Extração cancelada.';
    showToast('Cancelado.', 'error');
  }

  async function runExtraction() {
    if (isRunning) return;
    isRunning = true;
    shouldStop = false;
    accumulated = {};
    btnExtract.disabled = true;
    btnStop.disabled = false;
    btnExtract.innerHTML = '<div class="loader"></div> <span>Coletando…</span>';
    resultBox.classList.remove('active');

    try {
      statusText.innerHTML = '⏳ Injetando script…';
      await injectScript(tab.id);
      await new Promise(r => setTimeout(r, 500));

      statusText.innerHTML = '⏳ Extraindo perfil completo (expandido + scroll)…';
      const result = await sendAndWait(tab.id, { action: 'EXTRACT_STEP', step: 'MAIN' });

      if (shouldStop) return;

      if (!result.success) {
        statusText.innerHTML = `❌ Erro: ${result.error}`;
        showToast(`Erro: ${result.error}`, 'error');
        return;
      }

      accumulated = { ...result.data };

      extractedData = {
        fonte: 'trivor_linkedin_exporter',
        versao: '3.6.0',
        url: tab.url,
        idioma_detectado: 'pt',
        extraido_em: new Date().toISOString(),
        perfil: {
          nome: accumulated.nome || '',
          headline: accumulated.headline || '',
          localizacao: accumulated.localizacao || '',
          sobre: accumulated.sobre || '',
          preferencias_emprego: accumulated.preferencias_emprego || '',
          experiencias: accumulated.experiencias || [],
          atividades: accumulated.atividades || [],
          educacao: accumulated.educacao || [],
          certificacoes: accumulated.certificacoes || [],
          projetos: accumulated.projetos || [],
          habilidades: accumulated.habilidades || [],
          cursos: accumulated.cursos || [],
          idiomas: accumulated.idiomas || [],
          expansoes_realizadas: accumulated.expansoes || 0
        }
      };

      const jsonStr = JSON.stringify(extractedData, null, 2);
      jsonOutput.value = jsonStr;
      resultBox.classList.add('active');
      statusText.innerHTML = `🎉 Perfil de <strong>${extractedData.perfil.nome || 'Usuário'}</strong> exportado!`;
      showToast('Exportação concluída!', 'success');

    } catch (err) {
      if (!shouldStop) {
        statusText.innerHTML = `❌ Erro: ${err.message}`;
        showToast('Erro na extração.', 'error');
      }
    } finally {
      isRunning = false;
      btnExtract.disabled = false;
      btnStop.disabled = true;
      btnExtract.innerHTML = '⚡ Exportar Meu Perfil Completo';
    }
  }

  btnExtract.addEventListener('click', runExtraction);
  btnStop?.addEventListener('click', stopExtraction);

  btnCopy.addEventListener('click', async () => {
    if (!jsonOutput.value) return;
    try { await navigator.clipboard.writeText(jsonOutput.value); showToast('Copiado!', 'success'); }
    catch { showToast('Erro ao copiar.', 'error'); }
  });

  btnDownloadJson.addEventListener('click', () => {
    if (!extractedData) return;
    const blob = new Blob([JSON.stringify(extractedData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const name = extractedData.perfil?.nome?.replace(/\s+/g, '_') || 'perfil';
    a.href = url; a.download = `LinkedIn_${name}_Trivor.json`; a.click();
    URL.revokeObjectURL(url);
    showToast('Download JSON iniciado!', 'success');
  });

  btnDownloadMd.addEventListener('click', () => {
    if (!extractedData) return;
    const md = generateMarkdown(extractedData);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const name = extractedData.perfil?.nome?.replace(/\s+/g, '_') || 'perfil';
    a.href = url; a.download = `LinkedIn_${name}_Trivor.md`; a.click();
    URL.revokeObjectURL(url);
    showToast('Download Markdown iniciado!', 'success');
  });

  function generateMarkdown(p) {
    const d = p.perfil || {};
    const lines = ['# Perfil LinkedIn — ' + (d.nome || 'Usuário'), ''];
    lines.push('> Exportado via **Trivor Exporter** em ' + new Date(p.extraido_em).toLocaleString('pt-BR'));
    lines.push('');
    if (d.headline) lines.push('**Headline:** ' + d.headline + '\n');
    if (d.localizacao) lines.push('**Localização:** ' + d.localizacao + '\n');
    if (d.sobre) { lines.push('---\n## Sobre\n'); lines.push(d.sobre + '\n'); }
    if (d.preferencias_emprego) { lines.push('---\n## Preferências de Busca de Emprego\n'); lines.push(d.preferencias_emprego + '\n'); }
    if (d.experiencias?.length) { lines.push('---\n## Experiências Profissionais\n'); d.experiencias.forEach(e => lines.push('- ' + e)); lines.push(''); }
    const secs = [
      ['educacao', 'Formação Acadêmica'],
      ['certificacoes', 'Licenças e Certificações'],
      ['projetos', 'Projetos'],
      ['habilidades', 'Competências e Habilidades'],
      ['cursos', 'Cursos'],
      ['idiomas', 'Idiomas'],
      ['atividades', 'Atividades Recentes']
    ];
    for (const [k, title] of secs) {
      const val = d[k];
      if (val && (Array.isArray(val) ? val.length : (typeof val === 'string' && val.trim()))) {
        lines.push('---\n## ' + title + '\n');
        if (Array.isArray(val)) val.forEach(item => lines.push('- ' + item));
        else lines.push(val + '\n');
      }
    }
    return lines.join('\n');
  }
});