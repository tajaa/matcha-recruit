// Agency types
export type AgencyType = 'talent' | 'brand' | 'hybrid';
export type VerificationStatus = 'pending' | 'in_review' | 'verified' | 'rejected';
export type MemberRole = 'owner' | 'admin' | 'member';

// Agency
export interface Agency {
  id: string;
  name: string;
  slug: string;
  agency_type: AgencyType;
  description: string | null;
  logo_url: string | null;
  website_url: string | null;
  is_verified: boolean;
  verification_status: VerificationStatus;
  contact_email: string | null;
  industries: string[];
  created_at: string;
  updated_at: string;
}

export interface AgencyCreate {
  name: string;
  agency_type: AgencyType;
  description?: string;
  website_url?: string;
  contact_email?: string;
  industries?: string[];
}

export interface AgencyUpdate {
  name?: string;
  description?: string;
  logo_url?: string;
  website_url?: string;
  contact_email?: string;
  industries?: string[];
}

export interface AgencyPublic {
  id: string;
  name: string;
  slug: string;
  agency_type: AgencyType;
  description: string | null;
  logo_url: string | null;
  website_url: string | null;
  is_verified: boolean;
  industries: string[];
}

// Agency Member
export interface AgencyMember {
  id: string;
  agency_id: string;
  user_id: string;
  email: string;
  role: MemberRole;
  title: string | null;
  is_active: boolean;
  invited_at: string;
  joined_at: string | null;
}

export interface AgencyMemberInvite {
  email: string;
  role?: MemberRole;
  title?: string;
}

export interface AgencyMemberUpdate {
  role?: MemberRole;
  title?: string;
  is_active?: boolean;
}

// Agency with membership context
export interface AgencyWithMembership {
  agency: Agency;
  membership: AgencyMember;
  member_count: number;
  active_deals_count: number;
}

// Registration
export interface AgencyRegister {
  email: string;
  password: string;
  agency_name: string;
  agency_type: AgencyType;
  description?: string;
  website_url?: string;
  industries?: string[];
}
