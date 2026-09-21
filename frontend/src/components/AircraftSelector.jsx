import React, { useState, useRef, useEffect } from 'react'
import { ChevronDown, X, Layers } from 'lucide-react'

/**
 * AircraftSelector.jsx
 * ───────────────────────────────────────────────────────────────
 * Dropdown to select aircraft manuals or session documents.
 * Allows quick deselection to return to general/normal chat mode.
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
    <div className="relative flex items-center space-x-1.5" ref={wrapperRef}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Select active manual"
        className="flex items-center space-x-2.5 bg-navy-700 hover:bg-navy-600 px-3.5 py-1.5 rounded-lg transition-colors border border-navy-500"
      >
        <div 
          className="w-2.5 h-2.5 rounded-full" 
          style={{ backgroundColor: selected?.accent_color || (selected ? '#e8780a' : '#6b7280') }}
        ></div>
        <div className="text-left">
          <div className="text-[10px] text-gray-400 leading-none">Manual</div>
          <div className="font-semibold text-xs text-gray-200 truncate max-w-[140px] mt-0.5">
            {selected?.name || 'All Manuals (General)'}
          </div>
        </div>
        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Quick Deselect 1-Click Button */}
      {selected && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onSelect(null)
          }}
          title="Return to general chat (no manual filter)"
          aria-label="Deselect manual and return to normal chat"
          className="p-1.5 rounded-lg bg-navy-700/80 hover:bg-navy-600 text-gray-400 hover:text-orange border border-navy-500 transition-all flex items-center justify-center"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-72 bg-navy-800 border border-slate-border rounded-xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-2 space-y-1 max-h-72 overflow-y-auto">
            {/* General Mode Option */}
            <button
              onClick={() => {
                onSelect(null)
                setIsOpen(false)
              }}
              className={`w-full text-left p-2.5 rounded-lg transition-colors flex items-center space-x-2.5 ${
                !selected ? 'bg-navy-700 border border-orange/40 text-orange' : 'hover:bg-navy-700/60 text-gray-300'
              }`}
            >
              <Layers className="w-4 h-4 shrink-0 text-orange" />
              <div>
                <div className="font-semibold text-xs text-gray-100">All Manuals / General Chat</div>
                <div className="text-[10px] text-gray-400">Ask across all records or general flight questions</div>
              </div>
            </button>

            <div className="border-t border-navy-700 my-1"></div>

            <div className="text-[10px] font-mono text-gray-400 px-2 py-1 uppercase tracking-wider">
              Registered Manuals ({aircraftList.length})
            </div>

            {aircraftList.map((ac) => (
              <button
                key={ac.id}
                onClick={() => {
                  onSelect(ac)
                  setIsOpen(false)
                }}
                className={`w-full text-left p-2.5 rounded-lg transition-colors ${
                  selected?.id === ac.id ? 'bg-navy-700 border border-orange/40' : 'hover:bg-navy-700/60'
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="font-semibold text-xs text-gray-200 truncate mr-2">{ac.name}</div>
                  {ac.pdf_available && (
                    <span className="text-[10px] text-emerald-400 font-mono shrink-0">{ac.total_pages} pgs</span>
                  )}
                </div>
                {ac.nato_name && (
                  <div className="text-[10px] text-gray-400 mt-0.5">NATO: {ac.nato_name}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
