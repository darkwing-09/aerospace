import React, { useState, useImperativeHandle, forwardRef, useRef, useCallback, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'

// Use the matching worker version dynamically from unpkg to prevent version mismatches
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

/**
 * PdfViewer.jsx
 * ───────────────────────────────────────────────────────────────
 * Right-side PDF viewer with:
 *  - Single-page rendering for performance (no 330-page DOM bomb)
 *  - Page navigation controls
 *  - Zoom controls
 *  - jumpToPage(n) exposed via ref for auto-scroll from chat
 *  - Auto-loads PDF when aircraft is selected
 */

const PdfViewer = forwardRef(({ aircraftId, aircraftName }, ref) => {
  const [numPages, setNumPages] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [zoom, setZoom] = useState(1.2)
  const [loadError, setLoadError] = useState(null)
  const [highlightedPage, setHighlightedPage] = useState(null)
  const containerRef = useRef(null)

  // Reset page when aircraft changes
  useEffect(() => {
    setCurrentPage(1)
    setNumPages(null)
    setLoadError(null)
    setHighlightedPage(null)
  }, [aircraftId])

  // Expose jumpToPage to parent (called when model returns [PAGE_REF:N])
  useImperativeHandle(ref, () => ({
    jumpToPage: (pageNumber) => {
      if (pageNumber >= 1 && (!numPages || pageNumber <= numPages)) {
        setCurrentPage(pageNumber)
        setHighlightedPage(pageNumber)
        // Clear highlight after 3 seconds
        setTimeout(() => setHighlightedPage(null), 3000)
      }
    }
  }))

  const onDocumentLoadSuccess = useCallback(({ numPages: total }) => {
    setNumPages(total)
    setLoadError(null)
    console.log(`[PdfViewer] PDF loaded: ${total} pages`)
  }, [])

  const onDocumentLoadError = useCallback((error) => {
    console.error('[PdfViewer] PDF load error:', error)
    setLoadError(error.message || 'Failed to load PDF')
  }, [])

  const goToPage = useCallback((page) => {
    if (page >= 1 && page <= (numPages || 1)) {
      setCurrentPage(page)
    }
  }, [numPages])

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        goToPage(currentPage - 1)
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        goToPage(currentPage + 1)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [currentPage, goToPage])

  if (!aircraftId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-[#05070a]">
        <div className="text-gray-600 text-sm font-mono">Select an aircraft to view manual</div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col bg-navy-900 overflow-hidden relative">
      {/* PDF Header Controls */}
      <div className="h-12 border-b border-slate-border bg-navy-800/50 backdrop-blur-sm flex items-center justify-between px-4 z-20 shrink-0">
        <div className="flex items-center space-x-3">
          <span className="text-xs font-bold text-gray-400">MANUAL:</span>
          <span className="text-xs font-mono text-orange">{aircraftName || aircraftId}.PDF</span>
        </div>

        <div className="flex items-center space-x-3">
          {/* Page Navigation */}
          {numPages && (
            <div className="flex items-center space-x-1">
              <button 
                onClick={() => goToPage(1)}
                disabled={currentPage <= 1}
                className="px-1.5 py-0.5 text-[10px] font-mono hover:text-orange disabled:opacity-30 transition-colors"
                title="First page"
              >⏮</button>
              <button 
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage <= 1}
                className="px-1.5 py-0.5 text-[10px] font-mono hover:text-orange disabled:opacity-30 transition-colors"
                title="Previous page"
              >◀</button>
              
              <input
                type="number"
                value={currentPage}
                onChange={(e) => {
                  const val = parseInt(e.target.value)
                  if (val >= 1 && val <= numPages) setCurrentPage(val)
                }}
                className="w-12 text-center text-[10px] font-mono bg-navy-700 border border-navy-500 rounded px-1 py-0.5 text-orange focus:outline-none focus:border-orange"
                min={1}
                max={numPages}
              />
              <span className="text-[10px] font-mono text-gray-500">/ {numPages}</span>
              
              <button 
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage >= numPages}
                className="px-1.5 py-0.5 text-[10px] font-mono hover:text-orange disabled:opacity-30 transition-colors"
                title="Next page"
              >▶</button>
              <button 
                onClick={() => goToPage(numPages)}
                disabled={currentPage >= numPages}
                className="px-1.5 py-0.5 text-[10px] font-mono hover:text-orange disabled:opacity-30 transition-colors"
                title="Last page"
              >⏭</button>
            </div>
          )}

          {/* Zoom Controls */}
          <div className="flex items-center bg-navy-700 rounded-md p-1 border border-navy-500">
            <button 
              onClick={() => setZoom(prev => Math.max(0.5, prev - 0.2))}
              className="px-2 hover:text-orange transition-colors text-xs"
            >−</button>
            <span className="text-[10px] font-mono w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button 
              onClick={() => setZoom(prev => Math.min(3.0, prev + 0.2))}
              className="px-2 hover:text-orange transition-colors text-xs"
            >+</button>
          </div>
        </div>
      </div>

      {/* PDF Content Area */}
      <div 
        ref={containerRef}
        className="flex-1 overflow-auto p-6 flex flex-col items-center bg-[#0d1117]"
      >
        {loadError ? (
          <div className="py-20 text-center">
            <p className="text-danger font-bold uppercase text-sm mb-2">Error: PDF Link Severed</p>
            <p className="text-xs text-gray-500 mb-4">Verify backend/pdfs/{aircraftId}.pdf exists</p>
            <p className="text-xs text-gray-600 font-mono">{loadError}</p>
          </div>
        ) : (
          <Document
            file={`/api/pdf/${aircraftId}`}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={
              <div className="flex flex-col items-center py-20">
                <div className="w-10 h-10 border-4 border-navy-600 border-t-orange rounded-full animate-spin"></div>
                <p className="mt-4 text-xs font-mono text-gray-500 uppercase tracking-widest">Loading Manual…</p>
              </div>
            }
          >
            <div className={`relative transition-all duration-300 ${highlightedPage === currentPage ? 'ring-4 ring-orange/60 rounded-lg' : ''}`}>
              {/* Page number overlay */}
              <div className="absolute top-2 left-2 z-10 bg-navy-800/80 backdrop-blur-sm rounded px-2 py-0.5">
                <span className="text-[10px] font-mono text-gray-400">
                  PG {currentPage}{highlightedPage === currentPage && ' ← REFERENCED'}
                </span>
              </div>
              <Page
                pageNumber={currentPage}
                scale={zoom}
                renderTextLayer={false}
                renderAnnotationLayer={false}
                className="shadow-2xl"
                loading={
                  <div className="flex items-center justify-center py-40">
                    <div className="w-8 h-8 border-4 border-navy-600 border-t-orange rounded-full animate-spin"></div>
                  </div>
                }
              />
            </div>
          </Document>
        )}
      </div>

      {/* Quick scroll bar at bottom */}
      {numPages && (
        <div className="h-8 border-t border-slate-border bg-navy-800/80 flex items-center px-4 shrink-0">
          <input
            type="range"
            min={1}
            max={numPages}
            value={currentPage}
            onChange={(e) => setCurrentPage(parseInt(e.target.value))}
            className="w-full h-1 bg-navy-600 rounded-lg appearance-none cursor-pointer accent-orange"
          />
        </div>
      )}
    </div>
  )
})

PdfViewer.displayName = 'PdfViewer'
export default PdfViewer
