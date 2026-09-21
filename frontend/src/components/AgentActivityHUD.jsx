import React from 'react'
import { BrainCircuit, Image, Calculator, Sparkles, ShieldCheck, Package } from 'lucide-react'

/**
 * AgentActivityHUD.jsx
 * ───────────────────────────────────────────────────────────────
 * Renders real-time visual progress of the operations team.
 * Lucide SVG icons used consistently across all roles.
 */

function renderCapabilityIcon(capability, className = "w-4 h-4") {
  switch (capability) {
    case 'orchestrator':
    case 'supervisor':
    case 'planner':
      return <BrainCircuit className={className} />
    case 'vision_table':
    case 'visual':
    case 'visual_schematic':
      return <Image className={className} />
    case 'math':
    case 'avionics_physics':
      return <Calculator className={className} />
    case 'synthesis':
    case 'command_synthesis':
      return <Sparkles className={className} />
    case 'verification':
    case 'safety_validator':
    case 'safety_verification':
      return <ShieldCheck className={className} />
    case 'reasoning':
    case 'logistics':
    case 'logistics_inventory':
      return <Package className={className} />
    default:
      return <Sparkles className={className} />
  }
}

const DEFAULT_STAGES = [
  { id: 'planner', title: 'Understanding your question', capability: 'orchestrator' },
  { id: 'visual_schematic', title: 'Checking diagrams', capability: 'vision_table' },
  { id: 'avionics_physics', title: 'Running the calculation', capability: 'math' },
  { id: 'command_synthesis', title: 'Putting together the answer', capability: 'synthesis' },
  { id: 'safety_verification', title: 'Checking safety rules', capability: 'verification' },
]

function formatIntent(intent) {
  if (!intent) return 'Looking up answer...'
  const mapping = {
    SCHEMATIC_OR_PROCEDURE: 'Looking through diagrams and steps',
    VISUAL_AND_PHYSICS: 'Looking through diagrams and calculating',
    CALCULATION_OR_PHYSICS: 'Running the calculation',
    LOGISTICS_AND_PARTS: 'Checking parts and maintenance records',
    GENERAL_KNOWLEDGE: 'Searching flight manual',
  }
  return mapping[intent] || intent.replace(/_/g, ' ')
}

function getWorkerTitle(activeAgent, titleText) {
  const map = {
    supervisor: 'Understanding your question',
    orchestrator: 'Understanding your question',
    planner: 'Understanding your question',
    visual: 'Checking diagrams',
    vision_table: 'Checking diagrams',
    visual_schematic: 'Checking diagrams',
    math: 'Running the calculation',
    avionics_physics: 'Running the calculation',
    synthesis: 'Putting together the answer',
    command_synthesis: 'Putting together the answer',
    verification: 'Checking safety rules',
    safety_validator: 'Checking safety rules',
    safety_verification: 'Checking safety rules',
    logistics: 'Checking parts',
    reasoning: 'Checking parts',
  }
  return map[activeAgent] || titleText || 'Working on your question...'
}

export default function AgentActivityHUD({ agentStatus, isStreaming, mathSteps, dagPlan }) {
  if (!isStreaming && !agentStatus) return null

  const activeAgent = agentStatus?.agent || 'supervisor'
  const activeNodeId = agentStatus?.node_id || activeAgent
  const actionText = agentStatus?.action || 'Looking through flight manual records...'
  const titleText = getWorkerTitle(activeAgent, agentStatus?.title)

  // Use dynamic nodes from DAG plan if available, otherwise default template
  const rawNodes = dagPlan?.nodes && dagPlan.nodes.length > 0 ? dagPlan.nodes : DEFAULT_STAGES

  const isCurrentNode = (node) => {
    if (activeNodeId === node.id) return true
    if (activeAgent === node.capability || activeAgent === node.id) return true
    if (activeAgent === 'dispatcher' && (node.capability === 'vision_table' || node.capability === 'math' || node.capability === 'reasoning')) {
      return true
    }
    return false
  }

  return (
    <div className="mx-4 my-3 p-3.5 rounded-xl glass-panel-accent border border-orange/40 relative overflow-hidden shadow-2xl animate-in fade-in slide-in-from-top-2 duration-300">
      {/* Radar sweep effect */}
      <div className="radar-scanline"></div>

      {/* Header */}
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center space-x-2">
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-orange"></span>
          </span>
          <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-orange">
            Working on it...
          </span>
        </div>
        <div className="flex items-center space-x-2">
          {dagPlan?.intent && (
            <span className="text-[10px] text-orange/90 bg-orange/10 px-2 py-0.5 rounded border border-orange/30 font-medium">
              {formatIntent(dagPlan.intent)}
            </span>
          )}
        </div>
      </div>

      {/* Live Action Bar */}
      <div className="flex items-start space-x-2.5 bg-navy-800/90 p-2.5 rounded-lg border border-navy-600 mb-3">
        <div className="text-orange mt-0.5">
          {renderCapabilityIcon(activeAgent, "w-5 h-5")}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-bold text-gray-200">{titleText}</div>
          <div className="text-[11px] text-gray-400 mt-0.5 leading-snug truncate">
            {actionText}
          </div>
        </div>
      </div>

      {/* Operations Node Sequence */}
      <div className={`grid gap-1.5 pt-1 ${rawNodes.length <= 4 ? 'grid-cols-4' : rawNodes.length === 5 ? 'grid-cols-5' : 'grid-cols-6'}`}>
        {rawNodes.map((node, idx) => {
          const active = isCurrentNode(node)
          const label = getWorkerTitle(node.capability || node.id, node.title)

          return (
            <div
              key={node.id || idx}
              className={`flex flex-col items-center justify-center p-2 rounded-lg border text-center transition-all ${
                active
                  ? 'bg-orange/20 border-orange text-orange font-bold shadow-[0_0_14px_rgba(232,120,10,0.4)] scale-[1.03]'
                  : 'bg-navy-800/60 border-navy-700 text-gray-400'
              }`}
            >
              <div className="mb-1">
                {renderCapabilityIcon(node.capability || node.id, "w-3.5 h-3.5")}
              </div>
              <span className="text-[9px] font-mono leading-tight tracking-tight truncate w-full">
                {label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Calculations Evaluated */}
      {mathSteps && mathSteps.length > 0 && (
        <div className="mt-2.5 pt-2 border-t border-navy-700/80">
          <div className="text-[10px] font-mono text-emerald-400 font-bold uppercase mb-1 flex items-center space-x-1.5">
            <Calculator className="w-3.5 h-3.5" />
            <span>Calculations verified:</span>
          </div>
          {mathSteps.map((m, idx) => (
            <div key={idx} className="text-[10px] font-mono text-gray-300 bg-navy-900/80 p-1.5 rounded border border-navy-700">
              {m.summary}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
