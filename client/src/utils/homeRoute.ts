import type { UserRole } from '../types';

export function getAppHomePath(role?: UserRole | null): string {
  switch (role) {
    case 'candidate':
      return '/app/interviewer';
    case 'employee':
      return '/app/portal';
    case 'broker':
      return '/app/broker/clients';
    case 'admin':
    case 'client':
      return '/app';
    default:
      return '/';
  }
}
