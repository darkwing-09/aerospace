import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, AlertTriangle, Image as ImageIcon, Calculator } from 'lucide-react'
import VisualDiagramCard from './VisualDiagramCard'
import EvaluationScorecard from './EvaluationScorecard'
import { TacticalTTSButton } from './VoiceController'

/**
 * AgentThinkingAccordion
 * ───────────────────────────────────────────────────────────────
 * How I found this drawer.
 * By default COLLAPSED. Expands only when clicked.
 * Clean, plain language throughout with Lucide icons.
 */
function AgentThinkingAccordion({ thoughts, isStreaming, duration }) {
  const [isOpen, setIsOpen] = useState(false)

  if (!thoughts || thoughts.length === 0) {
    if (isStreaming) {
      return (
        <div className="mb-3.5 p-2.5 rounded-xl bg-navy-900/90 border border-orange/30 shadow-inner flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs text-orange">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span className="font-medium animate-pulse">
              Finding information in flight manual...
            </span>
          </div>
        </div>
      )
    }
    return null
  }

  const agentBadges = {
    supervisor: { label: 'Understanding question', bg: 'bg-orange/20 text-orange border-orange/40' },
    visual: { label: 'Checking diagrams', bg: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40' },
    math: { label: 'Running calculation', bg: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' },
    safety_validator: { label: 'Checking safety rules', bg: 'bg-amber-500/20 text-amber-400 border-amber-500/40' },
    synthesis: { label: 'Putting together answer', bg: 'bg-purple-500/20 text-purple-400 border-purple-500/40' },
    logistics: { label: 'Checking parts', bg: 'bg-blue-500/20 text-blue-400 border-blue-500/40' },
  }

  return (
    <div className="mb-4 rounded-xl border border-navy-600/80 bg-navy-900/80 overflow-hidden shadow-lg transition-all backdrop-blur-sm">
      {/* Accordion Toggle Header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-label="Toggle explanation of how answer was found"
        className="w-full flex items-center justify-between px-3.5 py-2 bg-navy-800/80 hover:bg-navy-700/80 text-left transition-colors"
      >
        <div className="flex items-center space-x-2.5">
          <span className="text-xs text-gray-300 font-medium flex items-center space-x-1.5">
            <span>How I found this {isOpen ? '▴' : '▾'}</span>
            {duration && (
              <span className="text-[11px] text-gray-400 font-normal">
                ({duration}s)
              </span>
            )}
          </span>
        </div>

        <div className="text-xs text-gray-400">
          <span>{isOpen ? 'Hide' : 'Details'}</span>
        </div>
      </button>

      {/* Accordion Body with Execution Timeline */}
      {isOpen && (
        <div className="p-3.5 space-y-3 bg-[#0c1017]/80 border-t border-navy-700/60 animate-in fade-in duration-200">
          {thoughts.map((t, idx) => {
            const badge = agentBadges[t.agent] || agentBadges.supervisor
            const isCompleted = t.status === 'completed'

            return (
              <div
                key={idx}
                className="relative pl-4 border-l-2 border-navy-600 hover:border-orange transition-colors text-left"
              >
                {/* Timeline node dot */}
                <div
                  className={`absolute -left-[5px] top-1.5 w-2 h-2 rounded-full ${
                    isCompleted ? 'bg-emerald-400' : 'bg-orange animate-pulse'
                  }`}
                ></div>

                {/* Step Header */}
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-[11px] font-medium text-gray-400">
                    Step {t.step || idx + 1}:
                  </span>

                  <span
                    className={`text-[10px] font-medium px-2 py-0.5 rounded border ${badge.bg}`}
                  >
                    {badge.label}
                  </span>
                </div>

                {/* Thought Details */}
                <p className="text-xs leading-relaxed text-gray-300 bg-navy-800/80 p-2.5 rounded-lg border border-navy-700/80 mt-1">
                  {t.thought}
                </p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/**
 * Custom Markdown Components with Tactical Styling
 */
const markdownComponents = {
  h1: ({ node, ...props }) => (
    <h1 className="text-base font-bold text-white mt-4 mb-2 tracking-wide border-b border-navy-600 pb-1" {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2 className="text-sm font-bold text-orange mt-3.5 mb-1.5 tracking-wide" {...props} />
  ),
  h3: ({ node, ...props }) => (
    <h3 className="text-xs font-bold text-cyan-400 mt-3 mb-1" {...props} />
  ),
  h4: ({ node, ...props }) => (
    <h4 className="text-xs font-bold text-gray-200 mt-2 mb-1" {...props} />
  ),
  p: ({ node, children, ...props }) => {
    // Detect [WARNING] tag
    if (typeof children === 'string' && children.includes('[WARNING]')) {
      const parts = children.split(/\[WARNING\]/i)
      return (
        <div className="my-2.5 p-3 rounded-lg tactical-alert-warning text-red-300 text-xs font-mono shadow-md">
          <div className="flex items-center space-x-1.5 font-bold text-red-400 uppercase mb-1">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <span>FLIGHT SAFETY WARNING</span>
          </div>
          <div className="leading-relaxed">{parts.join('')}</div>
        </div>
      )
    }

    // Detect [CAUTION] tag
    if (typeof children === 'string' && children.includes('[CAUTION]')) {
      const parts = children.split(/\[CAUTION\]/i)
      return (
        <div className="my-2.5 p-3 rounded-lg tactical-alert-caution text-amber-300 text-xs font-mono shadow-md">
          <div className="flex items-center space-x-1.5 font-bold text-amber-400 uppercase mb-1">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>OPERATIONAL CAUTION</span>
          </div>
          <div className="leading-relaxed">{parts.join('')}</div>
        </div>
      )
    }

    return <p className="mb-2.5 leading-relaxed text-sm text-gray-200 font-sans" {...props}>{children}</p>
  },
  strong: ({ node, ...props }) => (
    <strong className="font-semibold text-white" {...props} />
  ),
  code: ({ node, inline, ...props }) => (
    inline ? (
      <code className="text-xs font-mono bg-navy-900/90 text-orange px-1.5 py-0.5 rounded border border-navy-700" {...props} />
    ) : (
      <pre className="my-2.5 p-3 rounded-lg bg-[#070b10] border border-navy-700 text-xs font-mono text-gray-300 overflow-x-auto">
        <code {...props} />
      </pre>
    )
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote className="border-l-2 border-orange/80 pl-3.5 py-1.5 my-2.5 bg-navy-800/40 rounded-r-lg text-xs text-gray-300 italic" {...props} />
  ),
}

export default function MessageBubble({ message, onPageClick, onOpenInspector }) {
  const isAI = message.role === 'assistant'

  if (!isAI) {
    return (
      <div className="flex justify-end mb-5">
        <div className="max-w-[85%] bg-navy-700/90 border border-navy-500 rounded-2xl rounded-tr-none px-4 py-3 shadow-xl backdrop-blur-sm">
          <p className="text-sm leading-relaxed text-gray-100 font-sans">{message.content}</p>
        </div>
      </div>
    )
  }

  const isSafetyCritical =
    message.content?.includes('[WARNING]') ||
    message.content?.toLowerCase().includes('emergency') ||
    message.content?.toLowerCase().includes('flameout')

  return (
    <div className="flex justify-start mb-6 animate-in fade-in slide-in-from-left-2 duration-300">
      <div className="w-full bg-[#111622]/95 border border-navy-600/80 rounded-2xl p-5 shadow-2xl relative overflow-hidden backdrop-blur-md">
        {/* Left Accent Strip */}
        <div className="absolute top-0 left-0 w-1.5 h-full bg-gradient-to-b from-orange via-amber-500 to-orange/40"></div>

        {/* Top Meta Bar */}
        <div className="flex justify-between items-center mb-3.5 pb-2.5 border-b border-navy-700/60">
          <div className="flex items-center space-x-2">
            {isSafetyCritical && (
              <span className="text-[10px] bg-red-950/80 text-red-400 border border-red-800 px-2 py-0.5 rounded font-semibold flex items-center space-x-1">
                <AlertTriangle className="w-3 h-3 text-red-400" />
                <span>Safety-critical</span>
              </span>
            )}
          </div>

          <div className="flex items-center space-x-2">
            {message.content && <TacticalTTSButton text={message.content} />}

            {message.page_ref && (
              <button
                onClick={() => onPageClick && onPageClick(message.page_ref)}
                aria-label={`Jump to page ${message.page_ref}`}
                className="text-xs bg-navy-700 hover:bg-orange text-gray-200 hover:text-white border border-navy-500 hover:border-orange px-2.5 py-1 rounded-md transition-all font-medium shadow-sm"
              >
                Page {message.page_ref}
              </button>
            )}
          </div>
        </div>

        {/* Thinking Process Accordion (How I found this ▾) */}
        <AgentThinkingAccordion
          thoughts={message.thoughts}
          isStreaming={message.isStreaming}
          duration={message.thinkingDuration}
        />

        {/* 1. Visual Diagrams (Rendered FIRST) */}
        {message.visualRefs && message.visualRefs.length > 0 && (
          <div className="mb-4 p-3.5 bg-[#0b0f17]/90 border border-navy-700 rounded-xl shadow-lg">
            <div className="text-xs text-gray-300 font-medium mb-2.5 flex items-center justify-between">
              <span className="flex items-center space-x-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-orange" />
                <span>Manual Diagrams:</span>
              </span>
              <span className="text-[11px] text-gray-400">
                {message.visualRefs.length} found
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {message.visualRefs.map((vRef, vIdx) => (
                <VisualDiagramCard
                  key={vIdx}
                  visualRef={vRef}
                  onPageClick={onPageClick}
                />
              ))}
            </div>
          </div>
        )}

        {/* 2. Calculations (If Present, Rendered Before Text) */}
        {message.mathSteps && message.mathSteps.length > 0 && (
          <div className="mb-4 p-3 bg-emerald-950/20 border border-emerald-500/30 rounded-xl shadow-inner">
            <div className="text-xs text-emerald-400 font-medium mb-1.5 flex items-center space-x-1.5">
              <Calculator className="w-3.5 h-3.5" />
              <span>Calculations:</span>
            </div>
            <div className="space-y-1">
              {message.mathSteps.map((m, idx) => (
                <div key={idx} className="text-xs font-mono text-emerald-300">
                  {typeof m === 'string' ? m : m.result || m.step || JSON.stringify(m)}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 3. Formatted Live Streaming Markdown Content */}
        <div className="prose-tactical leading-relaxed text-sm text-gray-200">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {message.content}
          </ReactMarkdown>

          {message.isStreaming && (
            <span className="inline-block w-2 h-4 bg-orange ml-1 animate-pulse align-middle"></span>
          )}
        </div>

        {/* 4. Quality Evaluation Scorecard (Sources checked ✓) */}
        {message.evaluation && (
          <EvaluationScorecard
            evaluation={message.evaluation}
            onOpenInspector={onOpenInspector}
          />
        )}
      </div>
    </div>
  )
}
