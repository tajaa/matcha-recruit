type WorkAccess = { capabilities?: string[] } | null | undefined

function allows(access: WorkAccess, capability: string): boolean {
  return Boolean(access?.capabilities?.includes(capability))
}

export function canReviewEvents(access: WorkAccess): boolean {
  return allows(access, 'events.review')
}

export function canResolveEvents(access: WorkAccess): boolean {
  return allows(access, 'events.resolve')
}

export function canPromoteEvents(access: WorkAccess): boolean {
  return allows(access, 'events.promote')
}

export function canAssignEvents(access: WorkAccess): boolean {
  return allows(access, 'events.assign')
}
