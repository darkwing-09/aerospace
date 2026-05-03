import React, { useState, useRef, useEffect } from 'react'

/**
 * AircraftSelector.jsx
 * ───────────────────────────────────────────────────────────────
 * Dropdown to select fighter jets. Displays aircraft metadata
 * and PDF availability status.
 */

export default function AircraftSelector({ 
  aircraftList, 
  selected, 
  onSelect 
}) {
  const [isOpen, setIsOpen] = useState(false)
  const wrapperRef = useRef(null)

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={wrapperRef}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-3 bg-navy-600 hover:bg-navy-500 px-4 py-2 rounded-md transition-colors border border-navy-500"
      >
        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: selected?.accent_color || '#e8780a' }}></div>
        <div className="text-left">
          <div className="text-xs text-gray-400 font-bold tracking-tighter">SELECTED AIRCRAFT</div>
          <div className="font-bold text-sm">{selected?.name || 'Loading…'}</div>
        </div>
        <svg className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-64 bg-navy-700 border border-slate-border rounded-lg shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-2 space-y-1">
            {aircraftList.map((ac) => (
              <button
                key={ac.id}
                onClick={() => {
                  onSelect(ac)
                  setIsOpen(false)
                }}
                className={`w-full text-left p-3 rounded-md transition-colors ${
                  selected?.id === ac.id ? 'bg-navy-600' : 'hover:bg-navy-600/50'
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-bold text-sm">{ac.name}</div>
                    <div className="text-[10px] text-gray-400">NATO: {ac.nato_name}</div>
                  </div>
                  {!ac.pdf_available && (
                    <span className="bg-danger/20 text-danger text-[9px] px-1.5 py-0.5 rounded font-bold">NO PDF</span>
                  )}
                  {ac.pdf_available && (
                    <span className="text-[9px] text-success font-mono">{ac.total_pages} PGS</span>
                  )}
                </div>
                <div className="mt-2 text-[10px] text-gray-400 leading-tight">
                  Engine: {ac.engine}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
