// Page templates and collections share the same font-loading exclusion.
// Switching tabs while one prepares cannot queue a second layout.
export const layoutPreparation = new WeakSet<object>()
