'use client'
import { useState } from 'react';
import type { AnalysisResult } from '../types/analysis';
import { API_BASE_URL } from '../lib/api';
import { friendlyError } from '../lib/errors';

type ExportFormat = 'json' | 'md' | 'docx' | 'pdf';

/**
 * Estado + fluxo de exportação do diagnóstico (json/md/docx/pdf).
 * Vive fora do CurriculoTool para tirar 3 useStates e o handleExport
 * do componente main; a UI só recebe o valor pronto.
 */
export function useExport(
  res: AnalysisResult | null,
  fileName: string | null,
  jobTitle: string,
  jobLevel: string,
) {
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<ExportFormat>('pdf');

  const handleExport = async () => {
    if (!res) return;
    setExporting(exportFormat);
    setExportError(null);
    try {
      const formData = new FormData();
      formData.set('format', exportFormat);
      formData.set('filename', fileName || 'Curriculo.pdf');
      formData.set('job_target', `${jobTitle || 'Geral'} (${jobLevel})`);
      formData.set('data_json', JSON.stringify(res));

      const response = await fetch(`${API_BASE_URL}/api/export`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error('Falha ao gerar arquivo de exportação.');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Diagnostico_CV_${fileName?.replace('.pdf', '') || 'Analise'}.${exportFormat}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setExportError(friendlyError(err, 'Erro ao baixar o arquivo.'));
    } finally {
      setExporting(null);
    }
  };

  return { exporting, exportError, exportFormat, setExportFormat, handleExport };
}
