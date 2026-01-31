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
    requirements_count: number;
    unread_alerts_count: number;
}

export interface LocationCreate {
    name?: string;
    address?: string;
    city: string;
    state: string;
    county?: string;
    zipcode: string;
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

import { getAccessToken } from './client';

export const complianceAPI = {
    async getLocations(): Promise<BusinessLocation[]> {
        const response = await fetch('/api/compliance/locations', {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch locations');
        return response.json();
    },

    async getLocation(locationId: string): Promise<BusinessLocation> {
        const response = await fetch(`/api/compliance/locations/${locationId}`, {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch location');
        return response.json();
    },

    async createLocation(data: LocationCreate): Promise<BusinessLocation> {
        const response = await fetch('/api/compliance/locations', {
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

    async updateLocation(locationId: string, data: LocationUpdate): Promise<BusinessLocation> {
        const response = await fetch(`/api/compliance/locations/${locationId}`, {
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

    async deleteLocation(locationId: string): Promise<void> {
        const response = await fetch(`/api/compliance/locations/${locationId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to delete location');
    },

    async getRequirements(locationId: string, category?: string): Promise<ComplianceRequirement[]> {
        const params = category ? `?category=${category}` : '';
        const response = await fetch(`/api/compliance/locations/${locationId}/requirements${params}`, {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch requirements');
        return response.json();
    },

    async getAlerts(params?: { status?: string; severity?: string; limit?: number }): Promise<ComplianceAlert[]> {
        const searchParams = new URLSearchParams();
        if (params?.status) searchParams.set('status', params.status);
        if (params?.severity) searchParams.set('severity', params.severity);
        if (params?.limit) searchParams.set('limit', params.limit.toString());
        const query = searchParams.toString() ? `?${searchParams.toString()}` : '';

        const response = await fetch(`/api/compliance/alerts${query}`, {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch alerts');
        return response.json();
    },

    async markAlertRead(alertId: string): Promise<void> {
        const response = await fetch(`/api/compliance/alerts/${alertId}/read`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to mark alert as read');
    },

    async dismissAlert(alertId: string): Promise<void> {
        const response = await fetch(`/api/compliance/alerts/${alertId}/dismiss`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to dismiss alert');
    },

    async getSummary(): Promise<ComplianceSummary> {
        const response = await fetch('/api/compliance/summary', {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch summary');
        return response.json();
    },

    async checkCompliance(locationId: string): Promise<Response> {
        const response = await fetch(`/api/compliance/locations/${locationId}/check`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to start compliance check');
        return response;
    },

    async getCheckLog(locationId: string, limit?: number): Promise<CheckLogEntry[]> {
        const params = limit ? `?limit=${limit}` : '';
        const response = await fetch(`/api/compliance/locations/${locationId}/check-log${params}`, {
            headers: {
                'Authorization': `Bearer ${getAccessToken()}`,
            },
        });
        if (!response.ok) throw new Error('Failed to fetch check log');
        return response.json();
    },

    async getUpcomingLegislation(locationId: string): Promise<UpcomingLegislation[]> {
        const response = await fetch(`/api/compliance/locations/${locationId}/upcoming-legislation`, {
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
