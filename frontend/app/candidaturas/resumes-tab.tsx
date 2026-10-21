'use client'
import { useEffect, useRef, useState } from 'react'
import {
  FileText, UploadCloud, Trash2, Pencil, Loader2, Check, File,
} from 'lucide-react'
import {
  applyFetch, applyMethod, applyUpload,
  type ResumeItem, cardCls, btnPrimary, btnDanger, inputCls, labelCls,
} from './apply-api'

const EXT_OK = ['.pdf', '.docx']
const MAX_KB = 5 * 1024

export default function ResumesTab() {
  const [items, setItems] = useState<ResumeItem[] | null>(null)
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [perfil, setPerfil] = useState('')
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')
  const [arrastando, setArrastando] = useState(false)
  const [subindo, setSubindo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)
  const [editando, setEditando] = useState<ResumeItem | null>(null)
  const [edNome, setEdNome] = useState('')
  const [edDesc, setEdDesc] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const recarregar = () =>
    applyFetch('/api/apply/resumes')
      .then((d: { resumes: ResumeItem[] }) => setItems(d.resumes || []))
      .catch(e => setErro(e instanceof Error ? e.message : 'Falha ao listar currículos.'))
  useEffect(() => { recarregar() }, [])

  const aoEscolherArquivo = (f: File | null) => {
    if (!f) return
    const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
    if (!EXT_OK.includes(ext)) {
      setErro(`Formato "${ext || 'desconhecido'}" não é aceito. Use .pdf ou .docx.`)
      return
    }
    if (f.size > MAX_KB * 1024) {
      setErro(`Arquivo de ${Math.round(f.size / 1024)}KB passa do limite de 5MB.`)
      return
    }
    setErro(null)
    setArquivo(f)
  }

  const subir = async () => {
    if (!arquivo) return
    setSubindo(true)
    setErro(null)
    setOkMsg(null)
    try {
      const fd = new FormData()
      fd.append('file', arquivo)
      fd.append('perfil', perfil.trim() || 'geral')
      fd.append('nome', nome.trim() || arquivo.name)
      fd.append('descricao', descricao.trim())
      await applyUpload('/api/apply/resumes', fd)
      setArquivo(null)
      setPerfil('')
      setNome('')
      setDescricao('')
      if (fileRef.current) fileRef.current.value = ''
      setOkMsg('Currículo enviado. A IA já sabe do que se trata pela descrição.')
      await recarregar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha no upload.')
    } finally {
      setSubindo(false)
    }
  }

  const excluir = async (item: ResumeItem) => {
    if (!window.confirm(`Excluir "${item.nome || item.id}" da lista? O arquivo sai do apply/resumes.`)) return
    try {
      await applyMethod(`/api/apply/resumes/${item.id}`, 'DELETE')
      setOkMsg(`Currículo ${item.id} removido.`)
      if (editando?.id === item.id) setEditando(null)
      await recarregar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao excluir.')
    }
  }

  const salvarEdicao = async () => {
    if (!editando) return
    try {
      await applyMethod(`/api/apply/resumes/${editando.id}`, 'PATCH', {
        nome: edNome.trim() || editando.id,
        descricao: edDesc.trim(),
      })
      setEditando(null)
      await recarregar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao editar.')
    }
  }

  return (
    <div className="space-y-4">
      {/* ── Dropzone ── */}
      <div
        onDragOver={e => { e.preventDefault(); setArrastando(true) }}
        onDragLeave={() => setArrastando(false)}
        onDrop={e => {
          e.preventDefault()
          setArrastando(false)
          aoEscolherArquivo(e.dataTransfer.files?.[0] || null)
        }}
        className={`${cardCls} text-center transition-colors ${arrastando
          ? 'border-indigo-500/60 bg-indigo-500/10'
          : ''}`}>
        <div className={`mx-auto w-12 h-12 rounded-2xl flex items-center justify-center transition-colors ${arquivo
          ? 'bg-emerald-500/15 text-emerald-300'
          : 'bg-indigo-500/15 text-indigo-300'}`}>
          {arquivo ? <Check className="w-6 h-6" /> : <UploadCloud className="w-6 h-6" />}
        </div>
        <div className="mt-2 text-sm font-medium text-slate-200">
          {arquivo ? arquivo.name : 'Arraste o currículo aqui (PDF ou DOCX, até 5MB)'}
        </div>
        <div className="text-[11px] text-slate-500 mt-0.5">ou escolha o arquivo</div>
        <button onClick={() => fileRef.current?.click()} className={`${btnPrimary} mt-3`}>
          <File className="w-3.5 h-3.5" /> Escolher arquivo
        </button>
        <input ref={fileRef} type="file" accept=".pdf,.docx" className="hidden"
          onChange={e => aoEscolherArquivo(e.target.files?.[0] || null)} />
      </div>

      {/* ── Metadados pra IA ── */}
      {arquivo && (
        <div className={cardCls}>
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
            Descreva pra IA — ela usa isso pra escolher o currículo certo por vaga
          </div>
          <div className="mt-3 grid sm:grid-cols-3 gap-3">
            <div className="sm:col-span-1">
              <label className={labelCls}>Perfil</label>
              <input className={`${inputCls} mt-1`} value={perfil} onChange={e => setPerfil(e.target.value)}
                placeholder="ex.: backend_python, frontend, dados…" />
            </div>
            <div>
              <label className={labelCls}>Nome</label>
              <input className={`${inputCls} mt-1`} value={nome} onChange={e => setNome(e.target.value)}
                placeholder={arquivo.name} />
            </div>
            <div>
              <label className={labelCls}>Descrição</label>
              <input className={`${inputCls} mt-1`} value={descricao} onChange={e => setDescricao(e.target.value)}
                placeholder="ex.: focado em Python/FastAPI, 3 anos" />
            </div>
          </div>
          <button onClick={subir} disabled={subindo} className={`${btnPrimary} mt-4`}>
            {subindo ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UploadCloud className="w-3.5 h-3.5" />}
            Enviar currículo
          </button>
        </div>
      )}

      {/* ── Lista ── */}
      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
          Currículos enviados ({items?.length ?? '…'})
        </div>
        {erro && <div className="mt-2 text-xs text-rose-300">{erro}</div>}
        {okMsg && <div className="mt-2 text-xs text-emerald-300">{okMsg}</div>}
        <div className="mt-3 space-y-2">
          {(items || []).map(item => {
            const ed = editando?.id === item.id
            return (
              <div key={item.id}
                className={`rounded-xl border p-3 bg-slate-950/40 ${ed ? 'border-indigo-500/40' : 'border-slate-800/70'}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <FileText className="w-4 h-4 text-slate-500" />
                  <span className="text-sm font-medium text-slate-200">{item.nome || item.id}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full border border-slate-700 text-slate-400">
                    {item.id}
                  </span>
                  {!item.existe && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full border border-rose-500/40 text-rose-300">
                      arquivo ausente
                    </span>
                  )}
                  <span className="ml-auto flex gap-1.5">
                    <button onClick={() => { setEditando(item); setEdNome(item.nome); setEdDesc(item.descricao) }}
                      className="flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800/50 transition-colors">
                      <Pencil className="w-3 h-3" /> Editar
                    </button>
                    <button onClick={() => excluir(item)}
                      className="flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-lg border border-rose-500/40 text-rose-300 hover:bg-rose-500/10 transition-colors">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </span>
                </div>
                {ed ? (
                  <div className="mt-2 grid sm:grid-cols-2 gap-2">
                    <div>
                      <label className={labelCls}>Nome</label>
                      <input className={`${inputCls} mt-1`} value={edNome} onChange={e => setEdNome(e.target.value)} />
                    </div>
                    <div>
                      <label className={labelCls}>Descrição</label>
                      <input className={`${inputCls} mt-1`} value={edDesc} onChange={e => setEdDesc(e.target.value)} />
                    </div>
                    <div className="flex gap-2 sm:col-span-2">
                      <button onClick={salvarEdicao} className={btnPrimary}>
                        <Check className="w-3.5 h-3.5" /> Salvar
                      </button>
                      <button onClick={() => setEditando(null)}
                        className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800/50 transition-colors">
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  item.descricao && <div className="mt-1 text-xs text-slate-400">{item.descricao}</div>
                )}
              </div>
            )
          })}
          {items && items.length === 0 && (
            <div className="text-sm text-slate-500 py-4 text-center">
              Nenhum currículo ainda — arraste o primeiro acima.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
