import React from 'react'
import StatusBadge from './StatusBadge'

/**
 * MessageBubble.jsx
 * ───────────────────────────────────────────────────────────────
 * Formats AI responses. 
 * Supports:
 *   - Automatic StatusBadge detection
 *   - Step-based block formatting (Step N:)
 *   - Warning line coloring (WARNING:)
 *   - Clickable citation chips (REFERENCE: Page N)
 */

export default function MessageBubble({ message, onPageClick }) {
  const isAI = message.role === 'assistant'
  
  if (!isAI) {
    return (
      <div className="flex justify-end mb-6">
        <div className="max-w-[85%] bg-navy-600 border border-navy-500 rounded-2xl rounded-tr-none px-4 py-3 shadow-lg">
          <p className="text-sm leading-relaxed">{message.content}</p>
        </div>
      </div>
    )
  }

  // AI Formatting Logic
  const formatContent = (content) => {
    // Split into lines to process steps and warnings
    const lines = content.split('\n')
    const elements = []
    
    let currentStepBlock = []

    lines.forEach((line, i) => {
      const trimmed = line.trim()
      
      // 1. Step detection (e.g., Step 1:, 1., Step 1.)
      const stepMatch = trimmed.match(/^(Step\s+\d+:|\d+\.)\s+(.*)/i)
      
      // 2. Warning detection
      const isWarning = trimmed.toUpperCase().startsWith('WARNING:') || trimmed.toUpperCase().startsWith('CAUTION:')
      
      // 3. Section Headers (DIAGNOSIS:, PROCEDURE:, etc)
      const isHeader = /^[A-Z\s]{5,}:$/.test(trimmed)

      if (stepMatch) {
        elements.push(
          <div key={`step-${i}`} className="step-block">
            <span className="step-number">{stepMatch[1]}</span>
            <span className="text-sm">{stepMatch[2]}</span>
          </div>
        )
      } else if (isWarning) {
        elements.push(
          <p key={i} className="text-danger font-bold text-xs my-2 flex items-center">
            <span className="mr-2">⚠️</span> {trimmed}
          </p>
        )
      } else if (isHeader) {
        elements.push(
          <h4 key={i} className="text-[11px] font-black text-orange mt-4 mb-1 tracking-widest uppercase">
            {trimmed}
          </h4>
        )
      } else if (trimmed) {
        elements.push(
          <p key={i} className="text-sm leading-relaxed mb-2 text-gray-300">
            {trimmed}
          </p>
        )
      }
    })

    return elements
  }

  return (
    <div className="flex justify-start mb-8 animate-in fade-in slide-in-from-left-4 duration-300">
      <div className="w-full bg-slate-panel border border-slate-border rounded-xl px-5 py-4 shadow-xl relative overflow-hidden">
        {/* Accent Bar */}
        <div className="absolute top-0 left-0 w-1 h-full bg-orange"></div>

        <div className="flex justify-between items-center mb-4">
          <StatusBadge text={message.content} />
          {message.page_ref && (
            <button 
              onClick={() => onPageClick(message.page_ref)}
              className="text-[10px] font-mono bg-navy-600 hover:bg-navy-500 border border-navy-400 px-2 py-0.5 rounded text-orange transition-colors"
            >
              REF: PAGE {message.page_ref} ↗
            </button>
          )}
        </div>

        <div className="space-y-1">
          {formatContent(message.content)}
          {message.isStreaming && (
            <span className="inline-block w-2 h-4 bg-orange ml-1 animate-pulse align-middle"></span>
          )}
        </div>
      </div>
    </div>
  )
}
