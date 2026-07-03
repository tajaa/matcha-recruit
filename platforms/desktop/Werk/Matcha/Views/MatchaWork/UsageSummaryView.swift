import SwiftUI

struct UsageSummaryView: View {
    @State private var summary: MWUsageSummary?
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var periodDays = 30

    private func formatTokens(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Token Usage")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                Picker("", selection: $periodDays) {
                    Text("24h").tag(1)
                    Text("7d").tag(7)
                    Text("30d").tag(30)
                }
                .pickerStyle(.segmented)
                .frame(width: 140)
                .onChange(of: periodDays) { load() }
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 10)

            Divider().opacity(0.3)

            if isLoading {
                Spacer()
                HStack { Spacer(); ProgressView().tint(.secondary); Spacer() }
                Spacer()
            } else if let error = errorMessage {
                Spacer()
                Text(error)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity)
                Spacer()
            } else if let summary {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        // Totals
                        HStack(spacing: 20) {
                            StatBox(label: "Total Tokens", value: formatTokens(summary.totals.totalTokens))
                            StatBox(label: "Operations", value: "\(summary.totals.operationCount)")
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 12)

                        // By model
                        if !summary.byModel.isEmpty {
                            Text("By Model")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 16)

                            ForEach(summary.byModel) { model in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(model.model)
                                            .font(.system(size: 12, weight: .medium))
                                            .foregroundColor(.white)
                                        Text("\(formatTokens(model.totalTokens)) tokens · \(model.operationCount) ops")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    if let cost = model.costDollars, cost > 0 {
                                        Text("$\(String(format: "%.4f", cost))")
                                            .font(.system(size: 11))
                                            .foregroundColor(.matcha500)
                                    }
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 6)
                                .background(Color.zinc800.opacity(0.5))
                                .cornerRadius(8)
                                .padding(.horizontal, 12)
                            }
                        }
                    }
                    .padding(.bottom, 14)
                }
            }
        }
        .background(Color.appBackground)
        .task { load() }
    }

    private func load() {
        isLoading = true
        errorMessage = nil
        Task {
            do {
                let result = try await MatchaWorkService.shared.fetchUsageSummary(periodDays: periodDays)
                await MainActor.run {
                    summary = result
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

private struct StatBox: View {
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(.white)
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(Color.zinc800.opacity(0.5))
        .cornerRadius(8)
    }
}
