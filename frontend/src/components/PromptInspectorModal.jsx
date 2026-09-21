import React, { useState, useEffect } from 'react'
import { Activity, X } from 'lucide-react'

/**
 * PromptInspectorModal.jsx
 * ───────────────────────────────────────────────────────────────
 * Inspects LangSmith traces, multi-agent prompt construction,
 * sub-agent DAG decisions, and evaluation scorecards in real time.
 */

export default function PromptInspectorModal({ isOpen, onClose }) {
  const [tracesData, setTracesData] = useState(null)
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    const fetchTraces = async () => {
      setLoading(true)
      try {
        const res = await fetch('/api/prompts/inspect?limit=10')
        if (res.ok) {
          const data = await res.json()
          setTracesData(data)
          if (data.recent_traces?.length > 0) {
            setSelectedTrace(data.recent_traces[0])
          }
        }
      } catch (e) {
        console.error('[PromptInspector] Fetch error:', e)
      } finally {
        setLoading(false)
      }
    }

    fetchTraces()
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-6 animate-in fade-in duration-200">
      <div className="w-full max-w-5xl h-[85vh] bg-navy-800 border border-slate-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="h-16 px-6 border-b border-slate-border bg-navy-750 flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-3">
            <Activity className="w-5 h-5 text-orange" />
            <div>
              <div className="font-bold text-sm text-gray-200">
                AEROMIND PROMPT & LANGSMITH TRACE INSPECTOR
              </div>
              <div className="text-[10px] font-mono text-gray-400">
                PROJECT: {tracesData?.project || 'aeromind-defense-intel'} •{' '}
                <span className={tracesData?.cloud_enabled ? 'text-success' : 'text-orange'}>
                  {tracesData?.cloud_enabled ? 'LANGSMITH CLOUD SYNCED' : 'LOCAL TRACE BUFFER'}
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            aria-label="Close trace inspector"
            className="p-2 rounded-lg bg-navy-700 hover:bg-danger text-gray-300 hover:text-white transition-colors flex items-center space-x-1"
          >
            <X className="w-4 h-4" />
            <span className="text-xs">Close</span>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Trace List */}
          <div className="w-80 border-r border-slate-border bg-navy-900/60 p-3 overflow-y-auto space-y-2 shrink-0">
            <div className="text-[10px] font-mono font-bold text-gray-400 uppercase tracking-wider px-1 mb-2">
              Recent Execution Traces ({tracesData?.recent_traces?.length || 0})
            </div>

            {loading && (
              <div className="text-center py-8 text-xs font-mono text-gray-500 animate-pulse">
                Loading traces…
              </div>
            )}

            {tracesData?.recent_traces?.map((trace) => {
              const isSelected = selectedTrace?.run_id === trace.run_id
              return (
                <button
                  key={trace.run_id}
                  onClick={() => setSelectedTrace(trace)}
                  className={`w-full text-left p-2.5 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-orange/20 border-orange text-white shadow-lg'
                      : 'bg-navy-800/80 border-navy-700 hover:border-navy-500 text-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] font-mono text-gray-400 mb-1">
                    <span>{trace.aircraft_id?.toUpperCase()}</span>
                    <span>{Math.round(trace.latency_ms || 0)}ms</span>
                  </div>
                  <div className="text-xs font-medium truncate">{trace.query}</div>
                  <div className="mt-1.5 flex items-center space-x-2 text-[9px] font-mono text-gray-500">
                    <span>Eval: {trace.evaluation?.overall_confidence}%</span>
                    <span>•</span>
                    <span>{trace.timestamp?.substring(11, 19)}</span>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Right: Trace Detail View */}
          <div className="flex-1 p-6 overflow-y-auto space-y-5 bg-navy-800">
            {selectedTrace ? (
              <>
                {/* Query & Aircraft */}
                <div className="p-4 rounded-xl bg-navy-700/80 border border-slate-border">
                  <div className="text-[10px] font-mono text-orange uppercase font-bold tracking-wider mb-1">
                    User Query / Operational Command
                  </div>
                  <div className="text-sm font-semibold text-gray-100">{selectedTrace.query}</div>
                </div>

                {/* Multi-Agent DAG Plan */}
                <div className="p-4 rounded-xl bg-navy-700/80 border border-slate-border">
                  <div className="text-[10px] font-mono text-orange uppercase font-bold tracking-wider mb-2">
                    Supervisor Multi-Agent DAG Plan
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                    <div className="p-2.5 rounded bg-navy-800 border border-navy-600">
                      <div className="text-gray-400 text-[10px]">Parallel Branch Tasks:</div>
                      <div className="text-gray-200 mt-1">
                        {selectedTrace.plan?.parallel_tasks?.join(', ') || 'Default Multi-Aspect Retrieval'}
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-navy-800 border border-navy-600">
                      <div className="text-gray-400 text-[10px]">Sequential Validation:</div>
                      <div className="text-gray-200 mt-1">
                        {selectedTrace.plan?.sequential_tasks?.join(' → ') || 'Safety → Synthesis'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Quality Evaluation Breakdown */}
                <div className="p-4 rounded-xl bg-navy-700/80 border border-slate-border">
                  <div className="text-[10px] font-mono text-orange uppercase font-bold tracking-wider mb-2">
                    Real-Time Application Evaluation Scorecard
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-xs font-mono">
                    <div className="p-2.5 rounded bg-navy-800 border border-navy-600">
                      <div className="text-gray-400 text-[10px]">Faithfulness Grounding:</div>
                      <div className="text-lg font-bold text-success mt-0.5">
                        {selectedTrace.evaluation?.faithfulness_score}%
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-navy-800 border border-navy-600">
                      <div className="text-gray-400 text-[10px]">Citation Precision:</div>
                      <div className="text-lg font-bold text-success mt-0.5">
                        {selectedTrace.evaluation?.citation_score}%
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-navy-800 border border-navy-600">
                      <div className="text-gray-400 text-[10px]">Flight Safety Compliance:</div>
                      <div className="text-lg font-bold text-orange mt-0.5">
                        {selectedTrace.evaluation?.safety_compliance}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Raw Execution Payload */}
                <div className="p-4 rounded-xl bg-navy-900 border border-slate-border">
                  <div className="text-[10px] font-mono text-gray-400 uppercase font-bold tracking-wider mb-2">
                    Full JSON Trace Payload
                  </div>
                  <pre className="text-[11px] font-mono text-gray-300 overflow-x-auto max-h-60 p-3 bg-black/50 rounded-lg border border-navy-700">
                    {JSON.stringify(selectedTrace, null, 2)}
                  </pre>
                </div>
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500 font-mono text-sm">
                Select a trace on the left to inspect its prompt and multi-agent execution
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
