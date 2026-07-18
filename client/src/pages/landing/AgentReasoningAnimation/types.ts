export interface Decision {
  id: string
  label: string
  weighing: string[]      // ≥2 candidate citations the agent considers
  question: string         // the question the agent ultimately commits to
  result: 'GAP' | 'OK'
  remediation: string      // what the company must do
  cite: string             // the chosen statute
  status: string           // HUD line for this decision
}

export type Palette = { red: string; emerald: string; amber: string; live: string; neutral: string }

// Phase ordering for the loop
export type DecisionPhase = 'pending' | 'weighing' | 'committed' | 'remediated'

export interface DecisionState {
  phase: DecisionPhase
  weighIdx: number   // which candidate is currently "in focus" during weighing
}
