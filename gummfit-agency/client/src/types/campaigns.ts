// Campaign types for the limit order deal system

export type CampaignStatus = 'draft' | 'open' | 'active' | 'completed' | 'cancelled';
export type OfferStatus = 'pending' | 'viewed' | 'accepted' | 'declined' | 'expired' | 'taken';
export type CampaignPaymentType = 'upfront' | 'completion' | 'milestone' | 'affiliate';
export type CampaignPaymentStatus = 'pending' | 'held' | 'released' | 'refunded' | 'failed';
export type AffiliateEventType = 'click' | 'conversion';
export type TemplateType = 'sponsorship' | 'affiliate' | 'content' | 'ambassador' | 'custom';

// Campaign Deliverable
export interface CampaignDeliverable {
  type: string;
  quantity: number;
  description?: string;
  due_date?: string;
}

// Campaign Timeline
export interface CampaignTimeline {
  start_date?: string;
  end_date?: string;
  milestones?: Array<{ name: string; date: string }>;
}

// Campaign
export interface Campaign {
  id: string;
  agency_id: string;
  agency_name?: string;
  brand_name: string;
  title: string;
  description: string | null;
  deliverables: CampaignDeliverable[];
  timeline: CampaignTimeline;
  total_budget: number;
  upfront_percent: number;
  completion_percent: number;
  platform_fee_percent: number;
  max_creators: number;
  accepted_count: number;
  status: CampaignStatus;
  contract_template_id: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CampaignCreate {
  brand_name: string;
  title: string;
  description?: string;
  deliverables?: CampaignDeliverable[];
  timeline?: CampaignTimeline;
  total_budget: number;
  upfront_percent?: number;
  completion_percent?: number;
  platform_fee_percent?: number;
  max_creators?: number;
  contract_template_id?: string;
  expires_at?: string;
}

export interface CampaignUpdate {
  brand_name?: string;
  title?: string;
  description?: string;
  deliverables?: CampaignDeliverable[];
  timeline?: CampaignTimeline;
  total_budget?: number;
  upfront_percent?: number;
  completion_percent?: number;
  max_creators?: number;
  contract_template_id?: string;
  expires_at?: string;
}

// Campaign Offer
export interface CampaignOffer {
  id: string;
  campaign_id: string;
  campaign_title?: string;
  brand_name?: string;
  creator_id: string;
  creator_name?: string;
  creator_profile_image?: string;
  offered_amount: number;
  custom_message: string | null;
  status: OfferStatus;
  creator_counter_amount: number | null;
  creator_notes: string | null;
  viewed_at: string | null;
  responded_at: string | null;
  created_at: string;
}

export interface CampaignOfferCreate {
  creator_id: string;
  offered_amount: number;
  custom_message?: string;
}

export interface CampaignWithOffers extends Campaign {
  offers: CampaignOffer[];
  pending_offers_count: number;
  viewed_offers_count: number;
}

// Creator's view of an offer
export interface CreatorOffer {
  id: string;
  campaign_id: string;
  campaign_title: string;
  brand_name: string;
  agency_name: string;
  agency_verified: boolean;
  description: string | null;
  deliverables: CampaignDeliverable[];
  timeline: CampaignTimeline;
  offered_amount: number;
  custom_message: string | null;
  status: OfferStatus;
  creator_counter_amount: number | null;
  creator_notes: string | null;
  estimated_value_min: number | null;
  estimated_value_max: number | null;
  offer_vs_value_ratio: number | null;
  viewed_at: string | null;
  responded_at: string | null;
  created_at: string;
  expires_at: string | null;
}

// Campaign Payment
export interface CampaignPayment {
  id: string;
  campaign_id: string;
  creator_id: string;
  creator_name?: string;
  payment_type: CampaignPaymentType;
  amount: number;
  platform_fee: number | null;
  status: CampaignPaymentStatus;
  stripe_payment_intent_id: string | null;
  stripe_transfer_id: string | null;
  charged_at: string | null;
  released_at: string | null;
  created_at: string;
}

// Affiliate Link
export interface AffiliateLink {
  id: string;
  campaign_id: string | null;
  creator_id: string;
  creator_name?: string;
  agency_id: string;
  agency_name?: string;
  short_code: string;
  tracking_url: string;
  destination_url: string;
  product_name: string | null;
  commission_percent: number;
  platform_percent: number;
  click_count: number;
  conversion_count: number;
  total_sales: number;
  total_commission: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AffiliateLinkCreate {
  campaign_id?: string;
  creator_id: string;
  destination_url: string;
  product_name?: string;
  commission_percent?: number;
  platform_percent?: number;
}

export interface AffiliateLinkUpdate {
  destination_url?: string;
  product_name?: string;
  commission_percent?: number;
  is_active?: boolean;
}

export interface AffiliateStats {
  total_clicks: number;
  total_conversions: number;
  conversion_rate: number;
  total_sales: number;
  total_commission: number;
  pending_commission: number;
}

export interface AffiliateEvent {
  id: string;
  link_id: string;
  event_type: AffiliateEventType;
  sale_amount: number | null;
  commission_amount: number | null;
  ip_address: string | null;
  referrer: string | null;
  created_at: string;
}

// Creator Valuation
export interface ValuationFactors {
  follower_count?: number;
  engagement_rate?: number;
  niche_multiplier?: number;
  platform_rates?: Record<string, number>;
  audience_quality?: number;
  content_quality?: number;
  historical_deal_value?: number;
}

export interface CreatorValuation {
  id: string;
  creator_id: string;
  creator_name?: string;
  estimated_value_min: number;
  estimated_value_max: number;
  estimated_value_mid: number;
  factors: ValuationFactors;
  data_sources: string[];
  confidence_score: number | null;
  calculated_at: string;
}

// Contract Template
export interface ContractTemplate {
  id: string;
  agency_id: string | null;
  name: string;
  template_type: TemplateType | null;
  content: string;
  variables: string[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContractTemplateCreate {
  name: string;
  template_type: TemplateType;
  content: string;
  variables?: string[];
}

export interface ContractTemplateUpdate {
  name?: string;
  template_type?: TemplateType;
  content?: string;
  variables?: string[];
  is_default?: boolean;
}

export interface GeneratedContract {
  template_id: string;
  template_name: string;
  content: string;
  variables_used: Record<string, string>;
}

// Dashboard Stats
export interface CampaignDashboardStats {
  total_campaigns: number;
  active_campaigns: number;
  total_spent: number;
  pending_payments: number;
  total_creators_engaged: number;
  acceptance_rate: number;
}

export interface CreatorCampaignStats {
  total_offers_received: number;
  pending_offers: number;
  accepted_offers: number;
  total_earnings: number;
  pending_earnings: number;
  affiliate_earnings: number;
}
