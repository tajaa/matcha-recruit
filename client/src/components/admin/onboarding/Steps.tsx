/**
 * Six wizard steps for the master-admin onboarding flow. Each step lives
 * in its own file under `Steps/`; shared prop shape, primitives, and the
 * `isScopeEmpty` helper are in `Steps/_shared`. This barrel preserves the
 * historical `onboarding/Steps` import path (the steps are deliberately
 * thin — the heavy lifting lives in the backend `/expand` + `/resolve`
 * endpoints).
 */
export { Step1Basics } from './Steps/Step1Basics'
export { Step2Size } from './Steps/Step2Size'
export { Step3Locations } from './Steps/Step3Locations'
export { Step4Scope } from './Steps/Step4Scope'
export { Step5GapAnalysis } from './Steps/Step5GapAnalysis'
export { Step6Review } from './Steps/Step6Review'
