import React, { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

/**
 * EvaluationScorecard.jsx
 * ───────────────────────────────────────────────────────────────
 * Plain-language confidence and grounding confirmation.
 * Honestly labels unverified heuristic evaluations.
 * Omits invented default numbers.
 */

export default function EvaluationScorecard({ evaluation, onOpenInspector }) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!evaluation) return null

  const faithfulness = evaluation.heuristic_faithfulness ?? evaluation.faithfulness_score
  const citation = evaluation.heuristic_citation ?? evaluation.citation_score
  const safety_compliance = evaluation.safety_compliance ?? 'UNVERIFIED'
  const diagrams_verified = evaluation.diagrams_verified ?? 0
  const latency_ms = evaluation.latency_ms

  const isSafetyCritical = safety_compliance === 'CAUTION_REQUIRED' || safety_compliance === 'FAILED'

  return (
    <div className="mt-3 pt-2.5 border-t border-navy-700/60 text-xs">
      {/* Calm Summary Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="text-amber-400 font-medium flex items-center space-x-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span>Unverified (heuristic)</span>
          </span>
          {isSafetyCritical && (
            <span className="text-[10px] bg-red-950/60 text-red-400 border border-red-800 px-1.5 py-0.5 rounded font-medium">
              Safety check required
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2 text-[11px] text-gray-400">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            aria-expanded={isExpanded}
            aria-label="Toggle grounding and citation details"
            className="hover:text-gray-200 transition-colors flex items-center space-x-1"
          >
            <span>{isExpanded ? 'Hide details ▴' : 'Details ▾'}</span>
          </button>
        </div>
      </div>

      {/* Expanded Metrics Details */}
      {isExpanded && (
        <div className="mt-2.5 p-3 rounded-lg bg-navy-900/90 border border-navy-700 grid grid-cols-2 md:grid-cols-4 gap-2.5 animate-in fade-in duration-200 text-left">
          {/* Metric 1 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Manual Grounding</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {faithfulness != null ? `${faithfulness}%` : '—'}
            </div>
            {faithfulness != null && (
              <div className="w-full bg-navy-700 h-1 rounded-full mt-1.5 overflow-hidden">
                <div
                  className="bg-orange h-full rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, faithfulness))}%` }}
                ></div>
              </div>
            )}
          </div>

          {/* Metric 2 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Citation Accuracy</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {citation != null ? `${citation}%` : '—'}
            </div>
            {citation != null && (
              <div className="w-full bg-navy-700 h-1 rounded-full mt-1.5 overflow-hidden">
                <div
                  className="bg-success h-full rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, citation))}%` }}
                ></div>
              </div>
            )}
          </div>

          {/* Metric 3 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Diagrams Checked</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {diagrams_verified != null ? `${diagrams_verified} checked` : '—'}
            </div>
          </div>

          {/* Metric 4 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Response Time</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {latency_ms != null ? `${Math.round(latency_ms)} ms` : '—'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
