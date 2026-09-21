import React, { useState } from 'react'
import { Image, Maximize2, X, ZoomIn, ZoomOut } from 'lucide-react'

/**
 * VisualDiagramCard.jsx
 * ───────────────────────────────────────────────────────────────
 * Renders retrieved manual diagrams and cockpit schematics.
 * Features:
 * - Interactive preview card with Lucide icons
 * - Click-to-zoom modal for diagram inspection
 * - Instant "Sync PDF Reader" action
 */

export default function VisualDiagramCard({ visualRef, onPageClick }) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(1)

  if (!visualRef) return null

  const { page, is_schematic, image_url, thumbnail_b64, headings } = visualRef

  return (
    <>
      <div className="my-3 p-2.5 bg-navy-800/90 rounded-xl border border-navy-500/80 hover:border-orange/60 transition-all shadow-lg group text-left">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <Image className="w-3.5 h-3.5 text-orange" />
            <span className="text-xs font-semibold text-gray-200">
              {is_schematic ? 'Diagram schematic' : 'Manual diagram'}
            </span>
          </div>
          <button
            onClick={() => onPageClick && onPageClick(page)}
            aria-label={`Sync PDF to page ${page}`}
            className="text-[10px] font-mono bg-orange/20 hover:bg-orange text-orange hover:text-white px-2 py-0.5 rounded border border-orange/40 transition-colors"
          >
            Page {page} ↗
          </button>
        </div>

        {/* Thumbnail Preview Area */}
        <div
          className="relative rounded-lg overflow-hidden bg-[#0d1117] border border-navy-600 aspect-[16/9] flex items-center justify-center cursor-pointer group"
          onClick={() => setIsModalOpen(true)}
          role="button"
          tabIndex={0}
          aria-label={`Inspect page ${page} diagram`}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setIsModalOpen(true) }}
        >
          {image_url ? (
            <img
              src={image_url}
              alt={`Page ${page} diagram`}
              className="w-full h-full object-contain object-top group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
          ) : thumbnail_b64 ? (
            <img
              src={thumbnail_b64}
              alt={`Page ${page} thumb`}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform"
            />
          ) : (
            <div className="text-xs text-gray-500">Page {page} Diagram</div>
          )}

          {/* Hover overlay */}
          <div className="absolute inset-0 bg-navy-900/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center space-x-1.5 backdrop-blur-[2px]">
            <span className="text-xs bg-orange text-white px-3 py-1.5 rounded-lg shadow-lg font-medium flex items-center space-x-1.5">
              <Maximize2 className="w-3.5 h-3.5" />
              <span>Inspect Diagram</span>
            </span>
          </div>

          <div className="absolute bottom-1.5 left-1.5 bg-navy-900/80 px-2 py-0.5 rounded text-[9px] font-mono text-gray-300 border border-navy-700">
            Page {page}
          </div>
        </div>

        {headings && headings.length > 0 && (
          <div className="mt-2 text-[10px] text-gray-400 font-mono truncate">
            Ref: {headings.join(' • ')}
          </div>
        )}
      </div>

      {/* Full-Screen Diagram Lightbox Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col p-6 animate-in fade-in duration-200">
          {/* Top Bar */}
          <div className="flex items-center justify-between pb-4 border-b border-navy-700">
            <div className="flex items-center space-x-3">
              <span className="w-2.5 h-2.5 rounded-full bg-orange"></span>
              <span className="text-sm font-semibold text-gray-200">
                Diagram Inspector — Page {page}
              </span>
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={() => setZoomLevel((prev) => Math.max(0.7, prev - 0.2))}
                aria-label="Zoom out"
                className="px-2.5 py-1 bg-navy-700 hover:bg-navy-600 rounded text-xs text-gray-300 flex items-center space-x-1"
              >
                <ZoomOut className="w-3.5 h-3.5" />
                <span>Zoom</span>
              </button>
              <span className="text-xs font-mono text-orange">{Math.round(zoomLevel * 100)}%</span>
              <button
                onClick={() => setZoomLevel((prev) => Math.min(3.0, prev + 0.2))}
                aria-label="Zoom in"
                className="px-2.5 py-1 bg-navy-700 hover:bg-navy-600 rounded text-xs text-gray-300 flex items-center space-x-1"
              >
                <ZoomIn className="w-3.5 h-3.5" />
                <span>Zoom</span>
              </button>
              <button
                onClick={() => {
                  onPageClick && onPageClick(page)
                  setIsModalOpen(false)
                }}
                aria-label={`Jump to page ${page} in PDF reader`}
                className="px-3 py-1 bg-orange hover:bg-orange-light text-white rounded text-xs font-medium shadow-lg"
              >
                Open in reader ↗
              </button>
              <button
                onClick={() => setIsModalOpen(false)}
                aria-label="Close diagram inspector"
                className="p-1.5 bg-navy-700 hover:bg-danger text-gray-300 hover:text-white rounded transition-colors text-xs flex items-center space-x-1"
              >
                <X className="w-4 h-4" />
                <span>Close</span>
              </button>
            </div>
          </div>

          {/* Modal Image Viewport */}
          <div className="flex-1 overflow-auto flex items-center justify-center p-4">
            <img
              src={image_url}
              alt={`High-Res Page ${page}`}
              style={{ transform: `scale(${zoomLevel})` }}
              className="max-h-[85vh] max-w-[90vw] object-contain rounded shadow-2xl transition-transform duration-150"
            />
          </div>
        </div>
      )}
    </>
  )
}
