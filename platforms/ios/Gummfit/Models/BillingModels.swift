import Foundation
struct CappeSubscriptionAddon: Codable, Identifiable, Equatable { var id: String { code }; let code, name, unit_label: String; let quantity: Int }
struct CappeSubscription: Codable, Equatable { let plan_code, plan_name, interval, status, source: String?; let current_period_end, trial_end: String?; let cancel_at_period_end: Bool; let comped_until: String?; let addons: [CappeSubscriptionAddon]; let mailbox_quota: Int }
