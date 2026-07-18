import { FileText, Users, Presentation, Package, ClipboardList, Scale, BookOpen, FileCheck, MessageSquare, Briefcase, Languages } from 'lucide-react'

export const RESUME_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt']
export const RESUME_MAX_SIZE = 10 * 1024 * 1024
export const INVENTORY_EXTENSIONS = ['.csv', '.xlsx', '.xls']
// INVENTORY_EXTENSIONS is used in handleFileUpload for routing detection

// Skills available in the chat — requiresCompany gates visibility for individual users
export const HR_SKILLS = [
  { id: 'chat', icon: MessageSquare, label: 'HR Chat', desc: 'Ask any HR question', prompt: '', requiresCompany: false },
  { id: 'project', icon: FileText, label: 'Project', desc: 'Build reports & plans from chat', prompt: 'Create a new project called ', requiresCompany: false },
  { id: 'presentation', icon: Presentation, label: 'Presentation', desc: 'Generate slide decks', prompt: 'Create a presentation about ', requiresCompany: false },
  { id: 'resume_batch', icon: ClipboardList, label: 'Resume Batch', desc: 'Analyze candidate resumes', prompt: '', requiresCompany: false, dropHint: 'Drop resumes to start' },
  { id: 'inventory', icon: Package, label: 'Inventory', desc: 'Process invoices & track stock', prompt: '', requiresCompany: false, dropHint: 'Drop invoices to start' },
  { id: 'offer_letter', icon: FileCheck, label: 'Offer Letter', desc: 'Draft & send offer letters', prompt: 'Create an offer letter for ', requiresCompany: true },
  { id: 'handbook', icon: BookOpen, label: 'Handbook', desc: 'Generate employee handbooks', prompt: 'Create an employee handbook', requiresCompany: true },
  { id: 'policy', icon: Scale, label: 'Policy', desc: 'Draft compliance policies', prompt: 'Draft a policy for ', requiresCompany: true },
  { id: 'onboarding', icon: Users, label: 'Onboarding', desc: 'Create employee records', prompt: 'Onboard a new employee', requiresCompany: true },
  { id: 'review', icon: Briefcase, label: 'Review', desc: 'Run performance reviews', prompt: 'Create a performance review for ', requiresCompany: true },
  { id: 'language_tutor', icon: Languages, label: 'Language Tutor', desc: 'Practice English, Spanish, or French', prompt: '', requiresCompany: false },
] as const

export const PERSONAL_SKILLS = [
  { id: 'chat', icon: MessageSquare, label: 'Chat', desc: 'Research any topic', prompt: '', requiresCompany: false },
  { id: 'project', icon: FileText, label: 'Project', desc: 'Build documents from chat', prompt: 'Create a new project called ', requiresCompany: false },
  { id: 'presentation', icon: Presentation, label: 'Presentation', desc: 'Generate slide decks', prompt: 'Create a presentation about ', requiresCompany: false },
  { id: 'resume_batch', icon: ClipboardList, label: 'Resume Batch', desc: 'Analyze candidate resumes', prompt: '', requiresCompany: false, dropHint: 'Drop resumes to start' },
  { id: 'inventory', icon: Package, label: 'Inventory', desc: 'Process invoices & track stock', prompt: '', requiresCompany: false, dropHint: 'Drop invoices to start' },
  { id: 'language_tutor', icon: Languages, label: 'Language Tutor', desc: 'Practice English, Spanish, or French', prompt: '', requiresCompany: false },
] as const

export const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  offer_letter: 'Offer Letter',
  review: 'Review',
  workbook: 'Workbook',
  onboarding: 'Onboarding',
  presentation: 'Presentation',
  handbook: 'Handbook',
  policy: 'Policy',
  resume_batch: 'Resume Batch',
  inventory: 'Inventory',
  project: 'Project',
  language_tutor: 'Language Tutor',
}
