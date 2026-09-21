import React, { useState, useEffect, useRef } from 'react'
import { Folder, X, FileText, Image, Plus, Loader2 } from 'lucide-react'

/**
 * UniversalDocumentManager.jsx
 * ───────────────────────────────────────────────────────────────
 * Full Defense Data Center & Document Repository Manager.
 * Ingests and inspects multi-format datasets:
 * - PDF (Flight & systems manuals)
 * - DOCX (NATO standard operating procedures)
 * - CSV / XLSX (Logistics & ammunition stores)
 * - JSON (Avionics schemas & telemetry)
 * - Images (Cockpit schematics & blueprint photos)
 */

export default function UniversalDocumentManager({ isOpen, onClose, onSelectDocument }) {
  const [documents, setDocuments] = useState([])
  const [activeCategory, setActiveCategory] = useState('ALL')
  const [isUploading, setIsUploading] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [uploadCategory, setUploadCategory] = useState('AIRCRAFT_MANUAL')
  const [customName, setCustomName] = useState('')
  const [uploadDesc, setUploadDesc] = useState('')
  const fileInputRef = useRef(null)

  const fetchDocs = async () => {
    try {
      const res = await fetch('/api/documents/list')
      if (res.ok) {
        const data = await res.json()
        setDocuments(data)
        if (data.length > 0 && !selectedDoc) {
          setSelectedDoc(data[0])
        }
      }
    } catch (e) {
      console.error('[DocManager] Fetch error:', e)
    }
  }

  useEffect(() => {
    if (isOpen) {
      fetchDocs()
    }
  }, [isOpen])

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setIsUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('category', uploadCategory)
    if (customName) formData.append('custom_name', customName)
    if (uploadDesc) formData.append('description', uploadDesc)

    try {
      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      })
      if (res.ok) {
        await fetchDocs()
        setCustomName('')
        setUploadDesc('')
      } else {
        alert('File upload failed. Please try again.')
      }
    } catch (err) {
      console.error('[DocManager] Upload error:', err)
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (!isOpen) return null

  const categories = [
    { id: 'ALL', label: 'All Intelligence' },
    { id: 'AIRCRAFT_MANUAL', label: 'Flight Manuals (PDF)' },
    { id: 'TACTICAL_SOP', label: 'Tactical SOPs (DOCX)' },
    { id: 'LOGISTICS_INVENTORY', label: 'Logistics Manifests (CSV)' },
    { id: 'AVIONICS_TELEMETRY', label: 'Telemetry & Schematics' },
  ]

  const filteredDocs =
    activeCategory === 'ALL'
      ? documents
      : documents.filter((d) => d.category === activeCategory)

  return (
    <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-6 animate-in fade-in duration-200">
      <div className="w-full max-w-6xl h-[88vh] bg-navy-800 border border-slate-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="h-16 px-6 border-b border-slate-border bg-navy-750 flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-3">
            <Folder className="w-7 h-7 text-orange" />
            <div>
              <div className="font-bold text-base text-gray-200">
                MANUALS & DATASET REPOSITORY
              </div>
              <div className="text-[10px] font-mono text-gray-400">
                UNIVERSAL FORMAT SUPPORT (PDF, DOCX, CSV, XLSX, JSON, IMAGES)
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              aria-label="Upload dataset manual"
              className="px-4 py-2 bg-orange hover:bg-orange-light text-white rounded-xl text-xs font-bold shadow-lg flex items-center space-x-2 transition-all"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Ingesting Data…</span>
                </>
              ) : (
                <>
                  <Plus className="w-4 h-4" />
                  <span>Add Dataset</span>
                </>
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileUpload}
              className="hidden"
              accept=".pdf,.docx,.doc,.csv,.xlsx,.xls,.json,.txt,.log,.png,.jpg,.jpeg"
            />
            <button
              onClick={onClose}
              aria-label="Close repository modal"
              className="p-2 rounded-lg bg-navy-700 hover:bg-danger text-gray-300 hover:text-white transition-colors flex items-center space-x-1"
            >
              <X className="w-4 h-4" />
              <span className="text-xs">Close</span>
            </button>
          </div>
        </div>

        {/* Category Filter Pills */}
        <div className="px-6 py-2.5 border-b border-navy-700/80 bg-navy-900/60 flex items-center space-x-2 overflow-x-auto shrink-0">
          {categories.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveCategory(c.id)}
              className={`px-3 py-1 rounded-lg text-xs font-mono transition-all ${
                activeCategory === c.id
                  ? 'bg-orange text-white font-bold shadow-md'
                  : 'bg-navy-700/60 text-gray-400 hover:text-gray-200 hover:bg-navy-700'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* Body Layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Document Grid / List */}
          <div className="w-[45%] border-r border-slate-border p-4 overflow-y-auto space-y-3 bg-navy-900/40 shrink-0">
            <div className="text-[10px] font-mono font-bold text-gray-400 uppercase tracking-wider mb-2">
              Ingested Records ({filteredDocs.length})
            </div>

            {filteredDocs.map((doc) => {
              const isSelected = selectedDoc?.id === doc.id
              return (
                <div
                  key={doc.id}
                  onClick={() => setSelectedDoc(doc)}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-orange/15 border-orange text-white shadow-xl'
                      : 'bg-navy-800/90 border-navy-700 hover:border-navy-500 text-gray-300'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-bold text-sm text-gray-100">{doc.name}</div>
                      <div className="text-[10px] font-mono text-orange uppercase mt-0.5">
                        {doc.category} • {doc.file_type?.toUpperCase()}
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-gray-400 bg-navy-700 px-2 py-0.5 rounded border border-navy-600">
                      {doc.size_mb} MB
                    </span>
                  </div>

                  <p className="text-xs text-gray-400 mt-2 line-clamp-2 leading-relaxed">
                    {doc.description}
                  </p>

                  <div className="mt-3 flex items-center justify-between pt-2 border-t border-navy-700/60 text-[10px] font-mono text-gray-400">
                    <span>
                      {doc.total_pages ? `${doc.total_pages} Pages (ColPali Visual Indexed)` : 'Parsed Structured Data'}
                    </span>
                    {onSelectDocument && doc.file_type === 'pdf' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelectDocument(doc)
                          onClose()
                        }}
                        className="text-orange hover:underline font-bold"
                      >
                        Load in HUD ↗
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Right: Selected Document Detail / Table Preview */}
          <div className="flex-1 p-6 overflow-y-auto bg-navy-800 space-y-5">
            {selectedDoc ? (
              <>
                <div className="p-4 rounded-xl bg-navy-700/80 border border-slate-border">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-lg font-bold text-gray-100">{selectedDoc.name}</h3>
                      <div className="text-xs font-mono text-orange mt-1">
                        RECORD ID: {selectedDoc.id} • FORMAT: {selectedDoc.file_type?.toUpperCase()}
                      </div>
                    </div>
                    <span className="text-xs font-mono text-success bg-success/15 px-2.5 py-1 rounded-md border border-success/40">
                      RAG INDEXED
                    </span>
                  </div>
                  <p className="text-xs text-gray-300 mt-3 leading-relaxed">
                    {selectedDoc.description}
                  </p>
                </div>

                {/* If Tabular dataset (CSV/Excel) */}
                {selectedDoc.table_summary && (
                  <div className="p-4 rounded-xl bg-navy-900 border border-slate-border">
                    <div className="text-xs font-medium text-orange mb-3 flex items-center space-x-1.5">
                      <FileText className="w-4 h-4" />
                      <span>Tabular Dataset Preview ({selectedDoc.table_summary.row_count} Rows)</span>
                    </div>

                    <div className="overflow-x-auto max-h-72">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-navy-700/80 text-orange uppercase sticky top-0">
                          <tr>
                            {selectedDoc.table_summary.columns?.map((col) => (
                              <th key={col} className="p-2 border-b border-navy-600">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-navy-700/60 text-gray-300">
                          {selectedDoc.table_summary.preview_sample?.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-navy-800/80">
                              {selectedDoc.table_summary.columns?.map((col) => (
                                <td key={col} className="p-2 whitespace-nowrap">
                                  {String(row[col] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* If PDF Document */}
                {selectedDoc.file_type === 'pdf' && (
                  <div className="p-4 rounded-xl bg-navy-900 border border-slate-border">
                    <div className="text-xs font-medium text-orange mb-2 flex items-center space-x-1.5">
                      <Image className="w-4 h-4" />
                      <span>Manual Page Indexing Information</span>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-xs font-mono text-gray-300">
                      <div className="p-2.5 rounded bg-navy-800 border border-navy-700">
                        <div className="text-gray-500 text-[10px]">Total Pages:</div>
                        <div className="text-base font-bold text-gray-100 mt-1">
                          {selectedDoc.total_pages || 330}
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-navy-800 border border-navy-700">
                        <div className="text-gray-500 text-[10px]">Visual Schematics:</div>
                        <div className="text-base font-bold text-orange mt-1">
                          Rendered
                        </div>
                      </div>
                      <div className="p-2.5 rounded bg-navy-800 border border-navy-700">
                        <div className="text-gray-500 text-[10px]">VLM Status:</div>
                        <div className="text-base font-bold text-success mt-1">
                          Active Grounding
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500 font-mono text-sm">
                Select a dataset on the left to inspect its schema and contents
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
