// Labels shared by the AI Usage page (pages/admin/AiUsage.tsx) and its panels.

// The paid search APIs (search_apis.answer logs each request under its own
// provider). Their rows sit in the same ledger as model calls.
export const SEARCH_PROVIDERS: readonly string[] = ['brave', 'searchapi', 'serpapi', 'google_places']

// Every Espresso surface logs AI usage under this prefix (server:
// ai_usage_admin.ESPRESSO_FEATURE_PREFIX): assistant, tasks.<playbook>,
// job_search, agent_card, repo_question, task_draft.
export const ESPRESSO_FEATURE_PREFIX = 'matcha.espresso.'
