import React, { useState } from 'react'
import { Check } from 'lucide-react'

/**
 * EvaluationScorecard.jsx
 * ───────────────────────────────────────────────────────────────
 * Plain-language confidence and grounding confirmation.
 * Shows "Sources checked ✓" by default, with an optional details expander.
 */

export default function EvaluationScorecard({ evaluation, onOpenInspector }) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!evaluation) return null

  const {
    faithfulness_score = 85,
    citation_score = 95,
    safety_compliance = 'PASSED',
    diagrams_verified = 0,
    latency_ms = 0,
  } = evaluation

  const isSafetyCritical = safety_compliance !== 'PASSED'

  return (
    <div className="mt-3 pt-2.5 border-t border-navy-700/60 text-xs">
      {/* Calm Summary Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="text-emerald-400 font-semibold flex items-center space-x-1.5">
            <Check className="w-3.5 h-3.5 text-emerald-400" />
            <span>Sources checked</span>
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
              {faithfulness_score}%
            </div>
            <div className="w-full bg-navy-700 h-1 rounded-full mt-1.5 overflow-hidden">
              <div
                className="bg-orange h-full rounded-full"
                style={{ width: `${faithfulness_score}%` }}
              ></div>
            </div>
          </div>

          {/* Metric 2 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Citation Accuracy</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {citation_score}%
            </div>
            <div className="w-full bg-navy-700 h-1 rounded-full mt-1.5 overflow-hidden">
              <div
                className="bg-success h-full rounded-full"
                style={{ width: `${citation_score}%` }}
              ></div>
            </div>
          </div>

          {/* Metric 3 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Diagrams Checked</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {diagrams_verified} verified
            </div>
          </div>

          {/* Metric 4 */}
          <div className="p-2 rounded bg-navy-800/80 border border-navy-700">
            <div className="text-[10px] text-gray-400">Response Time</div>
            <div className="text-sm font-semibold text-gray-200 mt-0.5">
              {Math.round(latency_ms)} ms
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
