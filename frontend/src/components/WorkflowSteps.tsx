import type { ReactNode } from 'react'

export interface WorkflowStep {
  label: string
  detail: string
  state: 'complete' | 'current' | 'next'
  action?: ReactNode
}

export function WorkflowSteps({ steps }: { steps: WorkflowStep[] }) {
  return <ol className="workflow-steps" aria-label="\u6570\u636e\u96c6\u5de5\u4f5c\u6d41">
    {steps.map((step, index) => <li className={`workflow-step ${step.state}`} key={step.label}>
      <span className="workflow-number" aria-hidden="true">{index + 1}</span>
      <span className="workflow-copy"><strong>{step.label}</strong><small>{step.detail}</small></span>
      {step.action && <span className="workflow-action">{step.action}</span>}
    </li>)}
  </ol>
}
