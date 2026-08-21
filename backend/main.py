import sys
import re
import time
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Header, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter
from openai import OpenAI
import sqlite3, json, os, uuid

# Adiciona o diretório backend ao Python path para importar export_utils
backend_path = Path(__file__).parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from export_utils import generate_markdown_export, generate_docx_export, generate_pdf_export
from market_service import run_market_analysis, init_market_db, TECH_SYNONYMS

def _get_provider_for_tool(tool: str):
    """Retorna o melhor provider para uma ferramenta, ou None."""
    try:
        providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
        if not providers:
            return None
        # Prioridade: all > tool-specific > qualquer outra
        for priority in ['all', tool]:
            for p in providers:
                if p.get('usedFor') == priority and p.get('apiKey'):
                    return p
        # fallback: qualquer um com apiKey
        for p in providers:
            if p.get('apiKey'):
                return p
        return None
    except Exception:
        return None

app = FastAPI(title="Trivor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
KNOWLEDGE_DIR = BASE_DIR / 'knowledge'
PROMPT_FILE = KNOWLEDGE_DIR / 'system_prompt.md'
DB_FILE = DATA_DIR / 'database.db'

DATA_DIR.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            job_target TEXT,
            score REAL,
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()
converter = DocumentConverter()

def extract_text_from_pdf(pdf_path: str) -> str:
    # Extrator avançado: Lê o texto visual e extrai hiperlinks da camada de anotações (URIs e WebLinks)
    try:
        doc = pdfium.PdfDocument(pdf_path)
        page_outputs = []

        for page in doc:
            text_page = page.get_textpage()
            page_text = text_page.get_text_range()
            found_links = set()

            # 0. Busca URLs implícitas no texto (como "Abelウェアۃ LinkedIn" contendo link的功能)
            try:
                link_pattern = re.compile(r'(?i)(?:https?://|www\.|linkedin\.com|github\.com|github\.io)[^\s<>"]+', re.IGNORECASE)
                for match in link_pattern.finditer(page_text):
                    url = match.group()
                    found_links.add(url)
            except Exception:
                pass

            # 1. Extrai WebLinks (URLs explícitas via PDFium)
            try:
                weblinks = pdfium_c.FPDFLink_LoadWebLinks(text_page.raw)
                count = pdfium_c.FPDFLink_CountWebLinks(weblinks)
                for i in range(count):
                    buf_len = pdfium_c.FPDFLink_GetURL(weblinks, i, None, 0)
                    if buf_len > 0:
                        buffer = ctypes.create_string_buffer(buf_len * 2)
                        pdfium_c.FPDFLink_GetURL(weblinks, i, buffer, buf_len)
                        url = buffer.value.decode('utf-16le', errors='ignore').strip('\x00').strip()
                        if url:
                            found_links.add(url)
                pdfium_c.FPDFLink_CloseWebLinks(weblinks)
            except Exception:
                pass

            # 2. Extrai Hiperlinks Embutidos / Ancorados (ex: [Link do Projeto](https://...))
            try:
                annot_count = pdfium_c.FPDFPage_GetAnnotCount(page.raw)
                for i in range(annot_count):
                    annot = pdfium_c.FPDFPage_GetAnnot(page.raw, i)
                    if annot:
                        link = pdfium_c.FPDFAnnot_GetLink(annot)
                        if link:
                            action = pdfium_c.FPDFLink_GetAction(link)
                            if action:
                                buf_len = pdfium_c.FPDFAction_GetURIPath(doc.raw, action, None, 0)
                                if buf_len > 0:
                                    buffer = ctypes.create_string_buffer(buf_len)
                                    pdfium_c.FPDFAction_GetURIPath(doc.raw, action, buffer, buf_len)
                                    url = buffer.value.decode('utf-8', errors='ignore').strip('\x00').strip()
                                    if url:
                                        found_links.add(url)
                        pdfium_c.FPDFPage_CloseAnnot(annot)
            except Exception:
                pass

            # Concatena os links encontrados no texto da página para a IA analisar a acessibilidade
            if found_links:
                page_text += "\n\n--- [ Hiperlinks Clicáveis / Ancorados Detectados no Documento ] ---\n"
                for link_url in sorted(found_links):
                    page_text += f"• Link Clicável Ativo: {link_url}\n"

            page_outputs.append(page_text)

        extracted = "\n".join(page_outputs).strip()
        if extracted and len(extracted) > 20:
            return extracted
    except Exception:
        pass

    # Fallback para o Docling se necessário
    try:
        conversion_result = converter.convert(pdf_path)
        return conversion_result.document.export_to_markdown()
    except Exception as e:
        raise RuntimeError(f"Erro na extração de conteúdo do PDF: {str(e)}")

@app.get('/')
async def root():
    return {"status": "ok", "message": "Trivor Backend is running"}

@app.get('/health')
async def health_check():
    return {"status": "healthy"}

@app.post('/api/test-connection')
async def test_connection(
    api_key: str = Header(None, alias="api_key"),
    api_url: str = Header(None, alias="api_url"),
    model_name: str = Header(None, alias="model_name")
):
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key or key.strip() == "":
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    selected_model = model_name if (model_name and model_name.strip()) else "gpt-4o"
    base_url = api_url if (api_url and api_url.strip()) else None

    try:
        client = OpenAI(api_key=key, base_url=base_url)
        comp = client.chat.completions.create(
            model=selected_model,
            messages=[{'role': 'user', 'content': 'ping'}],
            max_tokens=5
        )
        return {"status": "ok", "message": f"Conexão bem-sucedida com o modelo '{selected_model}'!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha na conexão: {str(e)}")

@app.post('/api/analyze')
async def analyze(
    file: UploadFile = File(...),
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    job: str = Form(None),
    job_level: str = Form(None),
    provider_id: str = Form(None),
):
    # Se provider_id fornecido, buscar credenciais salvas
    if provider_id:
        try:
            providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
            prov = next((p for p in providers if p['id'] == provider_id), None)
            if prov and prov.get('usedFor') not in ('none', 'market'):
                api_key = prov['apiKey']
                api_url = prov.get('apiUrl') or api_url
                model_name = prov.get('modelName') or model_name
        except Exception:
            pass

    # Auto-select provider for curriculo if not provided
    if not api_key or not api_key.strip():
        prov = _get_provider_for_tool('curriculo')
        if prov:
            api_key = prov['apiKey']
            api_url = prov.get('apiUrl') or api_url
            model_name = prov.get('modelName') or model_name

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key or key.strip() == "":
        raise HTTPException(status_code=400, detail="Chave de API de IA não fornecida.")

    selected_model = model_name if (model_name and model_name.strip()) else "gpt-4o"
    base_url = api_url if (api_url and api_url.strip()) else None

    vaga_completa = f"{job or 'Não especificada'}"
    if job_level and job_level.strip() and job_level != "Sem nível específico":
        vaga_completa += f" (Nível: {job_level})"

    file_ext = Path(file.filename).suffix or ".pdf"
    safe_filename = f"{uuid.uuid4().hex}{file_ext}"
    saved_file_path = DATA_DIR / safe_filename

    try:
        content = await file.read()
        with open(saved_file_path, 'wb') as f:
            f.write(content)

        # Extração de texto ultra confiável
        markdown = extract_text_from_pdf(str(saved_file_path))

        if PROMPT_FILE.exists():
            with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
                sys_p = f.read()
        else:
            sys_p = "Você é um especialista em análise de currículos e diagnóstico ATS."

        instructions_prompt = (
            f"{sys_p}\n\n"
            "DIRETRIZES E REGRAS ESTRITAS DE AVALIAÇÃO:\n"
            "1. GROUNDING ESTRITO: Baseie-se APENAS nos dados extraídos do PDF enviado. Nunca invente fatos.\n"
            "2. FÓRMULA XYZ & STAR: Avalie se as experiências contêm a estrutura [Resultado (X)] + [Métrica/Número (Y)] + [Ação/Tech (Z)].\n"
            "3. CHECKLIST DE ERROS GRAVÍSSIMOS: Penalize severamente a presença de 'barras de porcentagem' de habilidades (ex: Python 80%), fotos desnecessárias, ou endereço residencial completo.\n"
            "4. REGRAS DE RESUMO PROFISSIONAL: Se o resumo contiver frases clichês vagas como 'apaixonado por inovação' sem apresentar números ou stack, recomende remoção imediata.\n"
            "5. ADEQUAÇÃO DA EDUCAÇÃO À SENIORIDADE: Para seniores/plenos, a seção de educação deve ser ultrassintética (1-2 linhas). Para juniores/estagiários, detalhe matérias e TCC se relevante.\n"
            "6. LEITURA DE DATAS E TEXTO: Reconheça com inteligência formatos comuns de datas de início e fim/previsão (ex: 'fev. De 2026 – Presente' significa início em fev/2026 e em andamento até o presente). Não acuse erro de data de início. Ignore pequenos artefatos de espaço da extração do PDF.\n"
            "7. ACESSIBILIDADE DE HIPERLINKS: Verifique atentamente a seção 'Hiperlinks Clicáveis / Ancorados Detectados no Documento' e o texto do CV. Se houver links do LinkedIn, GitHub ou Portfólio (seja via URL visível ou link embutido/ancorado), CONSIDERE COMO LINK VÁLIDO E CLICÁVEL em 'dados_pessoais'. NÃO alegue que o link é apenas texto simples se houver URLs extraídas ou detectadas no documento.\n\n"
            "Sua resposta DEVE SER EXCLUSIVAMENTE um objeto JSON válido (sem cercas ```json).\n"
            "A estrutura do JSON deve conter exatamente os seguintes campos:\n"
            "1. 'nota': número de 0 a 10.\n"
            "2. 'resumo_executivo': string direta com o parecer geral do currículo.\n"
            "3. 'pontos_fortes': lista de strings com aspectos positivos rastreáveis.\n"
            "4. 'diagnostico_por_secao': objeto onde cada chave é a seção do currículo:\n"
            "   - 'dados_pessoais': { 'status': 'ok'|'atencao'|'critico', 'problema': string, 'como_corrigir': string }\n"
            "   - 'resumo_profissional': { 'status': 'ok'|'atencao'|'critico', 'problema': string, 'como_corrigir': string }\n"
            "   - 'experiencia_profissional': { 'status': 'ok'|'atencao'|'critico', 'problema': string, 'como_corrigir': string }\n"
            "   - 'educacao_e_cursos': { 'status': 'ok'|'atencao'|'critico', 'problema': string, 'como_corrigir': string }\n"
            "   - 'habilidades_e_keywords': { 'status': 'ok'|'atencao'|'critico', 'problema': string, 'como_corrigir': string }\n"
            "5. 'analise_ats': {\n"
            "   'score_ats': número de 0 a 10,\n"
            "   'palavras_chave_faltantes': lista de strings com keywords essenciais para a vaga,\n"
            "   'gargalos_formatacao': lista de strings com problemas de parsing/formato,\n"
            "   'veredito_robos': string curta e objetiva sobre como os robôs enxergam esse CV\n"
            "}"
        )

        client = OpenAI(api_key=key, base_url=base_url)
        create_kwargs = {
            "model": selected_model,
            "messages": [
                {'role': 'system', 'content': instructions_prompt},
                {'role': 'user', 'content': f'Vaga Alvo / Nível: {vaga_completa}\n\nConteúdo do Currículo:\n{markdown}'}
            ]
        }

        if not base_url or 'openai.com' in base_url:
            create_kwargs["response_format"] = {'type': 'json_object'}

        start_time = time.time()
        comp = client.chat.completions.create(**create_kwargs)
        response_time_ms = (time.time() - start_time) * 1000

        raw_content = comp.choices[0].message.content or ""
        
        # Remove a tag <think>...</think> produzida por Modelos Pensadores (DeepSeek, etc)
        raw_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL)
        
        cleaned_content = raw_content.strip()
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content.split("\n", 1)[-1]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content.rsplit("```", 1)[0]
            cleaned_content = cleaned_content.strip()

        try:
            data = json.loads(cleaned_content)
        except Exception:
            data = {
                "nota": 6.5,
                "resumo_executivo": cleaned_content,
                "pontos_fortes": ["Conteúdo extraído com sucesso"],
                "diagnostico_por_secao": {},
                "analise_ats": {
                    "score_ats": 6.0,
                    "palavras_chave_faltantes": [],
                    "gargalos_formatacao": [],
                    "veredito_robos": cleaned_content
                }
            }

        if hasattr(comp, 'usage') and comp.usage:
            data['uso_tokens'] = {
                'prompt_tokens': comp.usage.prompt_tokens,
                'completion_tokens': comp.usage.completion_tokens,
                'total_tokens': comp.usage.total_tokens
            }
            data['api_info'] = {
                'model': comp.model,
                'request_id': comp.id,
                'response_time_ms': round(response_time_ms, 2)
            }

        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            'INSERT INTO analyses (filename, job_target, score, feedback) VALUES (?, ?, ?, ?)',
            (file.filename, vaga_completa, data.get('nota', 0), json.dumps(data))
        )
        conn.commit()
        conn.close()

        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a análise: {str(e)}")

@app.post('/api/export')
async def export_analysis(
    format: str = Form(...), # json, md, docx, pdf
    filename: str = Form(None),
    job_target: str = Form(None),
    model_name: str = Form(None),
    data_json: str = Form(...)
):
    try:
        data = json.loads(data_json)
        fname = filename or "curriculo.pdf"
        vaga = job_target or "Geral"
        model = model_name or "gpt-4o"

        if format == 'json':
            content = json.dumps(data, indent=2, ensure_ascii=False)
            return Response(
                content=content,
                media_type='application/json',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.json"'}
            )
        elif format == 'md':
            content = generate_markdown_export(data, fname, vaga, model)
            return Response(
                content=content,
                media_type='text/markdown',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.md"'}
            )
        elif format == 'docx':
            buffer = generate_docx_export(data, fname, vaga, model)
            return Response(
                content=buffer.getvalue(),
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.docx"'}
            )
        elif format == 'pdf':
            buffer = generate_pdf_export(data, fname, vaga, model)
            return Response(
                content=buffer.getvalue(),
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.pdf"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração do arquivo: {str(e)}")

@app.post('/api/market/analyze')
async def analyze_market(
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    job_title: str = Form(...),
    target_stack: str = Form(""),
    seniority: str = Form("Pleno"),
    location: str = Form("Remoto Nacional"),
    time_window: str = Form("90 dias")
):
    # Se provider_id fornecido, buscar credenciais salvas
    if provider_id:
        try:
            providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
            prov = next((p for p in providers if p['id'] == provider_id), None)
            if prov and prov.get('usedFor') not in ('none', 'curriculo'):
                api_key = prov['apiKey']
                api_url = prov.get('apiUrl') or api_url
                model_name = prov.get('modelName') or model_name
        except Exception:
            pass

    # Auto-select provider for market if not provided
    if not api_key or not api_key.strip():
        prov = _get_provider_for_tool('market')
        if prov:
            api_key = prov['apiKey']
            api_url = prov.get('apiUrl') or api_url
            model_name = prov.get('modelName') or model_name

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key or key.strip() == "":
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    selected_model = model_name if (model_name and model_name.strip()) else "gpt-4o"
    base_url = api_url if (api_url and api_url.strip()) else None

    try:
        client = OpenAI(api_key=key, base_url=base_url)
        report = run_market_analysis(
            db_file=DB_FILE,
            client=client,
            selected_model=selected_model,
            job_title=job_title,
            target_stack=target_stack,
            seniority=seniority,
            location=location,
            time_window=time_window
        )
        return {"success": True, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar inteligência de mercado: {str(e)}")

@app.get('/api/market/synonyms')
async def get_synonyms():
    return {"synonyms": TECH_SYNONYMS, "total": len(TECH_SYNONYMS)}
