/** Concise agent/human boundaries matching backend capabilities. Not marketing copy. */
export const AGENT_BOUNDARIES = [
  { actor: 'Agent 1', statement: 'Discovers process facts and evidence.' },
  { actor: 'Agent 3', statement: 'Finds eligible employees/resources using company directory data.' },
  { actor: 'Agent 4', statement: 'Coordinates workflow state, policy gates, approvals, and workflow planning.' },
  { actor: 'Agent 2', statement: 'Executes one authorized Workflow Step using a registered allow-listed tool.' },
  { actor: 'Human', statement: 'Approves or rejects controlled decisions.' },
  {
    actor: 'TO-BE',
    statement: 'Provides recommendations for human review; does not automatically change the workflow.',
  },
] as const
