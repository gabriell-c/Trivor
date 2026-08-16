/**
 * Trivor — LinkedIn Profile Exporter
 * Popup Logic
 */

'use strict';

document.addEventListener('DOMContentLoaded', async () => {
  const btnExtract = document.getElementById('btnExtract');
  const btnCopy = document.getElementById('btnCopy');
  const btnDownloadJson = document.getElementById('btnDownloadJson');
  const btnDownloadMd = document.getElementById('btnDownloadMd');
  const statusText = document.getElementById('statusText');
  const jsonOutput = document.getElementById('jsonOutput');
  const resultBox = document.getElementById('resultBox');
  const toast = document.getElementById('toast');

  let extractedData = null;

  function showToast(msg, type = 'success') {
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    setTimeout(() => {
      toast.className = 'toast';
    }, 3500);
  }

  // Verifica aba ativa
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab || !tab.url || !tab.url.includes('linkedin.com')) {
    statusText.innerHTML = '⚠️ Nenhuma página do <strong>LinkedIn</strong> detectada nesta aba. Acesse seu perfil para continuar.';
    btnExtract.disabled = true;
    return;
  }

  if (tab.url.includes('linkedin.com/in/')) {
    statusText.innerHTML = '✅ Perfil detectado! Clique no botão abaixo para iniciar a exportação dos seus dados.';
  } else {
    statusText.innerHTML = '💡 Navegue até o seu perfil (ex: <code>linkedin.com/in/seu-perfil</code>) para obter os dados completos.';
  }

  // Ação de extração
  btnExtract.addEventListener('click', async () => {
    btnExtract.disabled = true;
    btnExtract.innerHTML = '<div class="loader"></div> <span>Expandindo seções e coletando...</span>';
    statusText.innerHTML = '⏳ Coletando dados do perfil. Aguarde alguns segundos...';

    try {
      // Garante injeção do content script
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['src/content.js']
      }).catch(() => {}); // Ignora se já injetado

      // Envia mensagem ao content.js
      chrome.tabs.sendMessage(tab.id, { action: 'EXTRACT_PROFILE' }, (response) => {
        btnExtract.disabled = false;
        btnExtract.innerHTML = '⚡ Exportar Meu Perfil';

        if (chrome.runtime.lastError) {
          statusText.innerHTML = '❌ Erro ao se comunicar com a página. Recarregue o LinkedIn e tente novamente.';
          showToast('Falha na comunicação com a aba.', 'error');
          return;
        }

        if (response && response.success && response.data) {
          extractedData = response.data;
          const jsonStr = JSON.stringify(extractedData, null, 2);
          jsonOutput.value = jsonStr;
          resultBox.classList.add('active');
          statusText.innerHTML = '🎉 Perfil exportado com sucesso! Escolha o formato desejado abaixo.';
          showToast('Exportação concluída!', 'success');
        } else {
          statusText.innerHTML = `❌ Erro: ${response?.error || 'Não foi possível extrair os dados.'}`;
          showToast('Erro durante a extração.', 'error');
        }
      });

    } catch (err) {
      btnExtract.disabled = false;
      btnExtract.innerHTML = '⚡ Exportar Meu Perfil';
      statusText.innerHTML = `❌ Ocorreu um erro: ${err.message}`;
      showToast('Erro inesperado.', 'error');
    }
  });

  // Copiar JSON
  btnCopy.addEventListener('click', async () => {
    if (!jsonOutput.value) return;
    try {
      await navigator.clipboard.writeText(jsonOutput.value);
      showToast('JSON copiado para a área de transferência!', 'success');
    } catch {
      showToast('Erro ao copiar JSON.', 'error');
    }
  });

  // Download JSON
  btnDownloadJson.addEventListener('click', () => {
    if (!extractedData) return;
    const blob = new Blob([JSON.stringify(extractedData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const name = extractedData.dados?.nome ? extractedData.dados.nome.replace(/\s+/g, '_') : 'perfil';
    a.download = `LinkedIn_Perfil_${name}_Trivor.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Download do JSON iniciado!', 'success');
  });

  // Download Markdown
  btnDownloadMd.addEventListener('click', () => {
    if (!extractedData) return;
    const mdContent = generateMarkdown(extractedData);
    const blob = new Blob([mdContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const name = extractedData.dados?.nome ? extractedData.dados.nome.replace(/\s+/g, '_') : 'perfil';
    a.download = `LinkedIn_Perfil_${name}_Trivor.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Download do Markdown iniciado!', 'success');
  });

  function generateMarkdown(profile) {
    const d = profile.dados || {};
    const lines = [];
    lines.push(`# Perfil LinkedIn — ${d.nome || 'Usuário'}`);
    lines.push('');
    lines.push(`> Exportado via **Trivor Exporter** em ${new Date(profile.extraido_em).toLocaleString('pt-BR')}`);
    lines.push(`> Idioma detectado: \`${profile.idioma_detectado}\` | Fonte: [${profile.url}](${profile.url})`);
    lines.push('');
    if (d.headline) lines.push(`**Headline:** ${d.headline}\n`);
    if (d.localizacao) lines.push(`**Localização:** ${d.localizacao}\n`);

    if (d.about) {
      lines.push('## Sobre');
      lines.push(d.about);
      lines.push('');
    }

    if (Array.isArray(d.experiencias_detalhadas) && d.experiencias_detalhadas.length) {
      lines.push('## Experiências Profissionais');
      d.experiencias_detalhadas.forEach((e) => {
        lines.push(`- ${e.texto_bruto}`);
      });
      lines.push('');
    }

    const sectionsMap = {
      education: 'Formação Acadêmica',
      certifications: 'Licenças e Certificações',
      projects: 'Projetos',
      courses: 'Cursos',
      skills: 'Competências e Habilidades',
      languages: 'Idiomas',
      volunteer: 'Trabalho Voluntário',
      publications: 'Publicações',
      recommendations: 'Recomendações',
      honors: 'Prêmios e Honrarias',
      organizations: 'Organizações',
      featured: 'Destaques',
      activity: 'Atividade Recente'
    };

    for (const [key, title] of Object.entries(sectionsMap)) {
      const val = d[key];
      if (val && typeof val === 'string' && val.trim()) {
        lines.push(`## ${title}`);
        lines.push(val);
        lines.push('');
      }
    }
    return lines.join('\n');
  }
});