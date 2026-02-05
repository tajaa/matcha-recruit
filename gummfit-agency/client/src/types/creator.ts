// Platform types
export type Platform = 'youtube' | 'patreon' | 'tiktok' | 'instagram' | 'twitch' | 'twitter' | 'spotify';
export type SyncStatus = 'pending' | 'syncing' | 'synced' | 'failed';
export type RevenueCategory = 'adsense' | 'sponsorship' | 'affiliate' | 'merch' | 'subscription' | 'tips' | 'licensing' | 'services' | 'other';
export type ExpenseCategory = 'equipment' | 'software' | 'travel' | 'marketing' | 'contractors' | 'office' | 'education' | 'legal' | 'other';

// Creator Profile
export interface Creator {
  id: string;
  user_id: string;
  display_name: string;
  bio: string | null;
  profile_image_url: string | null;
  niches: string[];
  social_handles: Record<string, string>;
  audience_demographics: Record<string, unknown>;
  metrics: Record<string, unknown>;
  is_verified: boolean;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreatorCreate {
  display_name: string;
  bio?: string;
  niches?: string[];
  social_handles?: Record<string, string>;
  is_public?: boolean;
}

export interface CreatorUpdate {
  display_name?: string;
  bio?: string;
  profile_image_url?: string;
  niches?: string[];
  social_handles?: Record<string, string>;
  audience_demographics?: Record<string, unknown>;
  is_public?: boolean;
}

export interface CreatorPublic {
  id: string;
  display_name: string;
  bio: string | null;
  profile_image_url: string | null;
  niches: string[];
  audience_demographics: Record<string, unknown>;
  metrics: Record<string, unknown>;
  is_verified: boolean;
}

// Platform Connection
export interface PlatformConnection {
  id: string;
  creator_id: string;
  platform: Platform;
  platform_username: string | null;
  last_synced_at: string | null;
  sync_status: SyncStatus;
  sync_error: string | null;
  platform_data: Record<string, unknown>;
  created_at: string;
}

// Revenue Stream
export interface RevenueStream {
  id: string;
  creator_id: string;
  name: string;
  category: RevenueCategory;
  platform: string | null;
  description: string | null;
  is_active: boolean;
  tax_category: string | null;
  created_at: string;
}

export interface RevenueStreamCreate {
  name: string;
  category: RevenueCategory;
  platform?: string;
  description?: string;
  tax_category?: string;
}

export interface RevenueStreamUpdate {
  name?: string;
  category?: RevenueCategory;
  platform?: string;
  description?: string;
  is_active?: boolean;
  tax_category?: string;
}

// Revenue Entry
export interface RevenueEntry {
  id: string;
  creator_id: string;
  stream_id: string | null;
  stream_name: string | null;
  amount: number;
  currency: string;
  date: string;
  description: string | null;
  source: string | null;
  is_recurring: boolean;
  tax_category: string | null;
  created_at: string;
}

export interface RevenueEntryCreate {
  stream_id?: string;
  amount: number;
  currency?: string;
  date: string;
  description?: string;
  source?: string;
  is_recurring?: boolean;
  tax_category?: string;
}

export interface RevenueEntryUpdate {
  stream_id?: string;
  amount?: number;
  currency?: string;
  date?: string;
  description?: string;
  source?: string;
  is_recurring?: boolean;
  tax_category?: string;
}

// Expense
export interface Expense {
  id: string;
  creator_id: string;
  amount: number;
  currency: string;
  date: string;
  category: ExpenseCategory;
  description: string;
  vendor: string | null;
  receipt_url: string | null;
  is_deductible: boolean;
  tax_category: string | null;
  created_at: string;
}

export interface ExpenseCreate {
  amount: number;
  currency?: string;
  date: string;
  category: ExpenseCategory;
  description: string;
  vendor?: string;
  is_deductible?: boolean;
  tax_category?: string;
}

export interface ExpenseUpdate {
  amount?: number;
  currency?: string;
  date?: string;
  category?: ExpenseCategory;
  description?: string;
  vendor?: string;
  receipt_url?: string;
  is_deductible?: boolean;
  tax_category?: string;
}

// Dashboard/Analytics
export interface RevenueSummary {
  total_revenue: number;
  total_expenses: number;
  net_income: number;
  revenue_by_category: Record<string, number>;
  revenue_by_stream: Record<string, number>;
  expenses_by_category: Record<string, number>;
  period_start: string;
  period_end: string;
}

export interface MonthlyRevenue {
  month: string;
  revenue: number;
  expenses: number;
  net: number;
}

export interface RevenueOverview {
  current_month: RevenueSummary;
  previous_month: RevenueSummary;
  year_to_date: RevenueSummary;
  monthly_trend: MonthlyRevenue[];
}

// Registration
export interface CreatorRegister {
  email: string;
  password: string;
  display_name: string;
  bio?: string;
  niches?: string[];
  social_handles?: Record<string, string>;
}
