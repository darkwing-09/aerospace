import React from 'react'
import { AlertTriangle, Wrench, ClipboardList, FileText, Layers, Package } from 'lucide-react'

/**
 * StatusBadge.jsx
 * ───────────────────────────────────────────────────────────────
 * Renders a stylized badge based on detected problem type with Lucide SVG icons.
 * Priority keywords: EMERGENCY, FAULT, PROCEDURE, SPEC, COMPONENT, SYSTEM.
 */

export default function StatusBadge({ text }) {
  const detectType = (t) => {
    if (!t) return 'default'
    const lower = t.toLowerCase()
    if (lower.includes('emergency')) return 'emergency'
    if (lower.includes('fault') || lower.includes('error')) return 'fault'
    if (lower.includes('procedure') || lower.includes('step')) return 'procedure'
    if (lower.includes('spec') || lower.includes('limit')) return 'spec'
    if (lower.includes('system')) return 'system'
    if (lower.includes('component') || lower.includes('part')) return 'component'
    return 'default'
  }

  const type = detectType(text)

  const configs = {
    emergency: { label: 'EMERGENCY', color: 'bg-danger text-white', icon: <AlertTriangle className="w-3 h-3 mr-1" /> },
    fault:     { label: 'FAULT DIAGNOSIS', color: 'bg-danger text-white', icon: <Wrench className="w-3 h-3 mr-1" /> },
    procedure: { label: 'PROCEDURE', color: 'bg-orange text-white', icon: <ClipboardList className="w-3 h-3 mr-1" /> },
    spec:      { label: 'SPECIFICATION', color: 'bg-purple-600 text-white', icon: <FileText className="w-3 h-3 mr-1" /> },
    system:    { label: 'SYSTEM OVERVIEW', color: 'bg-success text-white', icon: <Layers className="w-3 h-3 mr-1" /> },
    component: { label: 'COMPONENT', color: 'bg-blue-600 text-white', icon: <Package className="w-3 h-3 mr-1" /> },
    default:   { label: 'MAINTENANCE', color: 'bg-gray-600 text-white', icon: <Wrench className="w-3 h-3 mr-1" /> },
  }

  const { label, color, icon } = configs[type] || configs.default

  return (
    <div className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${color}`}>
      {icon}
      <span>{label}</span>
    </div>
  )
}
