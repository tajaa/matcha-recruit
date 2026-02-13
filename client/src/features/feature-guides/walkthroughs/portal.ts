import type { WalkthroughConfig } from '../types';

export const portalOnboardingWalkthrough: WalkthroughConfig = {
  id: 'portal-onboarding',
  title: 'Onboarding Checklist',
  category: 'employee',
  steps: [
    {
      target: 'portal-onboard-progress',
      title: 'Your Progress',
      content: 'This card shows how many onboarding tasks you have completed out of the total.',
      placement: 'bottom',
      expect: 'A progress bar with completed and pending counts.',
      ifMissing: 'The progress card appears when you have assigned onboarding tasks.',
    },
    {
      target: 'portal-onboard-my-tasks',
      title: 'Your Tasks',
      content: 'These are the onboarding tasks assigned to you. Complete them to finish your onboarding.',
      placement: 'bottom',
      expect: 'A list of tasks with category icons and completion buttons.',
      ifMissing: 'No tasks assigned to you yet. Check back later.',
    },
    {
      target: 'portal-onboard-complete-btn',
      title: 'Mark Complete',
      content: 'Click this button when you have finished a task. It will be marked as done.',
      placement: 'left',
      action: 'Click "Mark Complete" on any pending task.',
      ifMissing: 'This button appears on tasks that are not yet completed.',
    },
    {
      target: 'portal-onboard-hr-tasks',
      title: 'HR/Manager Tasks',
      content: 'These tasks are handled by your HR team or manager. You can track their progress here.',
      placement: 'top',
      expect: 'A section with tasks and their current status (pending or done).',
      ifMissing: 'HR tasks appear when your company has assigned manager-side onboarding steps.',
    },
  ],
};

export const portalDocumentsWalkthrough: WalkthroughConfig = {
  id: 'portal-documents',
  title: 'My Documents',
  category: 'employee',
  steps: [
    {
      target: 'portal-docs-filters',
      title: 'Filter Documents',
      content: 'Filter between All documents, Pending signatures, or already Signed documents.',
      placement: 'bottom',
      action: 'Click a filter button to narrow the list.',
    },
    {
      target: 'portal-docs-list',
      title: 'Documents List',
      content: 'All documents assigned to you by your company — policies, handbooks, and agreements.',
      placement: 'top',
      expect: 'Document cards with titles, types, and status badges.',
      ifMissing: 'No documents have been assigned to you yet.',
    },
    {
      target: 'portal-docs-status',
      title: 'Document Status',
      content: 'Each document shows its current status — Pending Signature, Signed, or Expired.',
      placement: 'left',
      expect: 'A colored status badge on each document.',
    },
    {
      target: 'portal-docs-sign-btn',
      title: 'Sign Document',
      content: 'Click to digitally sign a pending document. You will type your full name to confirm.',
      placement: 'left',
      action: 'Click "Sign" on a pending document to open the signing dialog.',
      ifMissing: 'Sign buttons appear only on documents pending your signature.',
    },
  ],
};

export const portalPTOWalkthrough: WalkthroughConfig = {
  id: 'portal-pto',
  title: 'Time Off',
  category: 'employee',
  steps: [
    {
      target: 'portal-pto-balance',
      title: 'PTO Balance',
      content: 'Your available hours, total balance, used hours, and year-to-date accrual.',
      placement: 'bottom',
      expect: 'Four cards with hour amounts.',
      ifMissing: 'Balance data loads from your HR system. If missing, PTO may not be configured yet.',
    },
    {
      target: 'portal-pto-request-btn',
      title: 'Request Time Off',
      content: 'Submit a new PTO request with dates, hours, and an optional reason.',
      placement: 'bottom',
      action: 'Click to open the time-off request form.',
    },
    {
      target: 'portal-pto-pending',
      title: 'Pending Requests',
      content: 'Requests waiting for manager approval. You can cancel pending requests if plans change.',
      placement: 'bottom',
      expect: 'Request cards with dates, hours, and a cancel button.',
      ifMissing: 'No pending requests. Submit a new request to see it here.',
    },
    {
      target: 'portal-pto-approved',
      title: 'Approved Time Off',
      content: 'Your confirmed time off for the current year.',
      placement: 'top',
      expect: 'Request cards with dates, hours, and a green "Approved" badge.',
      ifMissing: 'No approved time off yet this year.',
    },
    {
      target: 'portal-pto-cancel-btn',
      title: 'Cancel Request',
      content: 'Cancel a pending request if your plans change. This cannot be undone.',
      placement: 'left',
      action: 'Click the X icon next to a pending request to cancel it.',
      ifMissing: 'Cancel buttons appear only on pending requests.',
    },
  ],
};
