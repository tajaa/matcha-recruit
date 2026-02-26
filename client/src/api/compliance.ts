export interface BusinessLocation {
    id: string;
    company_id: string;
    name: string | null;
    address: string | null;
    city: string;
    state: string;
    county: string | null;
    zipcode: string;
    is_active: boolean;
    auto_check_enabled: boolean;
    auto_check_interval_days: number;
    next_auto_check: string | null;
    last_compliance_check: string | null;
    created_at: string;
    has_local_ordinance: boolean | null;
    requirements_count: number;
    unread_alerts_count: number;
}

export interface LocationCreate {
    name?: string;
    address?: string;
    city: string;
    state: string;
    county?: string;
    zipcode?: string;
}

export interface JurisdictionOption {
    city: string;
    state: string;
    county: string | null;
    has_local_ordinance: boolean;
}

export interface LocationUpdate {
    name?: string;
    address?: string;
    city?: string;
    state?: string;
    county?: string;
    zipcode?: string;
    is_active?: boolean;
}

export interface ComplianceRequirement {
    id: string;
    category: string;
    rate_type: string | null;
    jurisdiction_level: string;
    jurisdiction_name: string;
    title: string;
    description: string | null;
    current_value: string | null;
    numeric_value: number | null;
    source_url: string | null;
    source_name: string | null;
    effective_date: string | null;
    previous_value: string | null;
    last_changed_at: string | null;
}

export interface VerificationSource {
    url: string;
    name: string;
    type: 'official' | 'news' | 'blog' | 'other';
    snippet?: string;
}

export interface ComplianceAlert {
    id: string;
    location_id: string;
    requirement_id: string | null;
    title: string;
    message: string;
    severity: 'info' | 'warning' | 'critical';
    status: 'unread' | 'read' | 'dismissed' | 'actioned';
    category: string | null;
    action_required: string | null;
    source_url: string | null;
    source_name: string | null;
    deadline: string | null;
    confidence_score: number | null;
    verification_sources: VerificationSource[] | null;
    alert_type: 'change' | 'new_requirement' | 'upcoming_legislation' | 'deadline_approaching' | null;
    effective_date: string | null;
    metadata: Record<string, unknown> | null;
    created_at: string;
    read_at: string | null;
}

export interface CheckLogEntry {
    id: string;
    location_id: string;
    company_id: string;
    check_type: 'manual' | 'scheduled' | 'proactive';
    status: 'running' | 'completed' | 'failed';
    started_at: string;
    completed_at: string | null;
    new_count: number;
    updated_count: number;
    alert_count: number;
    error_message: string | null;
}

export interface UpcomingLegislation {
    id: string;
    location_id: string;
    category: string | null;
    title: string;
    description: string | null;
    current_status: 'proposed' | 'passed' | 'signed' | 'effective_soon' | 'effective' | 'dismissed';
    expected_effective_date: string | null;
    impact_summary: string | null;
    source_url: string | null;
    source_name: string | null;
    confidence: number | null;
    days_until_effective: number | null;
    created_at: string;
}

export interface ComplianceSummary {
    total_locations: number;
    total_requirements: number;
    unread_alerts: number;
    critical_alerts: number;
    recent_changes: {
        location: string;
        category: string;
        title: string;
        old_value: string | null;
        new_value: string;
        changed_at: string;
    }[];
    auto_check_locations: number;
    upcoming_deadlines: {
        title: string;
        effective_date: string;
        days_until: number;
        status: string;
        category: string | null;
        location: string;
    }[];
}

/** A single item in the coming_up list returned by GET /compliance/dashboard */
export interface ComplianceDashboardItem {
    legislation_id: string;
    title: string;
    description: string | null;
    category: string | null;
    /** Inferred or alert-linked severity: 'info' | 'warning' | 'critical' */
    severity: 'info' | 'warning' | 'critical';
    status: string;
    effective_date: string | null;
    days_until: number | null;
    location_id: string;
    location_name: string;
    location_state: string;
    affected_employee_count: number;
    /** Up to 5 sample employee names for display */
    affected_employee_sample: string[];
    /** Precision level — 'state_estimate' until Phase 2 exact FK is wired */
    impact_basis: 'state_estimate' | 'exact';
    source_url: string | null;
}

export interface ComplianceDashboard {
    kpis: {
        total_locations: number;
        unread_alerts: number;
        critical_alerts: number;
        employees_at_risk: number;
    };
    coming_up: ComplianceDashboardItem[];
}

import { getAccessToken } from './client';

function companyParam(url: string, companyId?: string): string {
    if (!companyId || typeof companyId !== 'string') return url;
    return url.includes('?') ? `${url}&company_id=${companyId}` : `${url}?company_id=${companyId}`;
}

export const complianceAPI = {
    async getJurisdictions(): Promise<JurisdictionOption[]> {
        const response = await fetch('/api/compliance/jurisdictions', {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch jurisdictions');
        return response.json();
    },

    async getLocations(companyId?: string): Promise<BusinessLocation[]> {
        const response = await fetch(companyParam('/api/compliance/locations', companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch locations');
        return response.json();
    },

    async getLocation(locationId: string, companyId?: string): Promise<BusinessLocation> {
        const response = await fetch(companyParam(`/api/compliance/locations/${locationId}`, companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch location');
        return response.json();
    },

    async createLocation(data: LocationCreate, companyId?: string): Promise<BusinessLocation> {
        const response = await fetch(companyParam('/api/compliance/locations', companyId), {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });
        if (!response.ok) throw new Error('Failed to create location');
        return response.json();
    },

    async updateLocation(locationId: string, data: LocationUpdate, companyId?: string): Promise<BusinessLocation> {
        const response = await fetch(companyParam(`/api/compliance/locations/${locationId}`, companyId), {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });
        if (!response.ok) throw new Error('Failed to update location');
        return response.json();
    },

    async deleteLocation(locationId: string, companyId?: string): Promise<void> {
        const response = await fetch(companyParam(`/api/compliance/locations/${locationId}`, companyId), {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to delete location');
    },

    async getRequirements(locationId: string, category?: string, companyId?: string): Promise<ComplianceRequirement[]> {
        let url = `/api/compliance/locations/${locationId}/requirements`;
        if (category) url += `?category=${category}`;
        const response = await fetch(companyParam(url, companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch requirements');
        return response.json();
    },

    async getAlerts(params?: { status?: string; severity?: string; limit?: number }, companyId?: string): Promise<ComplianceAlert[]> {
        const searchParams = new URLSearchParams();
        if (params?.status) searchParams.set('status', params.status);
        if (params?.severity) searchParams.set('severity', params.severity);
        if (params?.limit) searchParams.set('limit', params.limit.toString());
        const query = searchParams.toString() ? `?${searchParams.toString()}` : '';

        const response = await fetch(companyParam(`/api/compliance/alerts${query}`, companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch alerts');
        return response.json();
    },

    async markAlertRead(alertId: string, companyId?: string): Promise<void> {
        const response = await fetch(companyParam(`/api/compliance/alerts/${alertId}/read`, companyId), {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to mark alert as read');
    },

    async dismissAlert(alertId: string, companyId?: string): Promise<void> {
        const response = await fetch(companyParam(`/api/compliance/alerts/${alertId}/dismiss`, companyId), {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to dismiss alert');
    },

    async getSummary(companyId?: string): Promise<ComplianceSummary> {
        const response = await fetch(companyParam('/api/compliance/summary', companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch summary');
        return response.json();
    },

    async getDashboard(horizonDays: 30 | 60 | 90 | 180 | 365 = 90, companyId?: string): Promise<ComplianceDashboard> {
        const url = `/api/compliance/dashboard?horizon_days=${horizonDays}`;
        const response = await fetch(companyParam(url, companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch compliance dashboard');
        return response.json();
    },

    async checkCompliance(locationId: string, companyId?: string): Promise<Response> {
        const response = await fetch(companyParam(`/api/compliance/locations/${locationId}/check`, companyId), {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to start compliance check');
        return response;
    },

    async getCheckLog(locationId: string, limit?: number, companyId?: string): Promise<CheckLogEntry[]> {
        let url = `/api/compliance/locations/${locationId}/check-log`;
        if (limit) url += `?limit=${limit}`;
        const response = await fetch(companyParam(url, companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch check log');
        return response.json();
    },

    async getUpcomingLegislation(locationId: string, companyId?: string): Promise<UpcomingLegislation[]> {
        const response = await fetch(companyParam(`/api/compliance/locations/${locationId}/upcoming-legislation`, companyId), {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch upcoming legislation');
        return response.json();
    },
};

export const COMPLIANCE_CATEGORY_LABELS: Record<string, string> = {
    minimum_wage: 'Minimum Wage',
    overtime: 'Overtime',
    sick_leave: 'Sick Leave',
    meal_breaks: 'Meal & Rest Breaks',
    pay_frequency: 'Pay Frequency',
    final_pay: 'Final Pay',
    minor_work_permit: 'Minor Work Permits',
    scheduling_reporting: 'Scheduling & Reporting Time',
    workers_comp: "Workers' Comp",
    business_license: 'Business License',
    tax_rate: 'Tax Rate',
    posting_requirements: 'Posting Requirements',
};

export const JURISDICTION_LEVEL_LABELS: Record<string, string> = {
    federal: 'Federal',
    state: 'State',
    county: 'County',
    city: 'City',
};

export const ALERT_SEVERITY_COLORS: Record<string, string> = {
    info: 'blue',
    warning: 'amber',
    critical: 'red',
};
