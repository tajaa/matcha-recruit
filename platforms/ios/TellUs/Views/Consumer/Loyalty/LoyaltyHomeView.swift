import SwiftUI

struct LoyaltyHomeView: View {
    @State private var programs: [LoyaltyProgramSummary] = []
    @State private var error: String?

    var body: some View {
        Group {
            if programs.isEmpty, error == nil {
                ProgressView()
            } else if programs.isEmpty {
                EmptyState(icon: "sparkles", title: "No brand programs yet", hint: error)
            } else {
                List(programs) { program in
                    NavigationLink {
                        LoyaltyBrandView(brandID: program.brand_id)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(program.brand_name).font(.interBody.bold())
                            Text(program.name).font(.interCaption).foregroundStyle(TU.textDim)
                            Text("\(program.points_balance) \(program.point_plural)")
                                .font(.interCaption.bold()).foregroundStyle(TU.ember)
                        }
                        .padding(.vertical, 5)
                    }
                    .listRowBackground(TU.inkRaised)
                }
                .listStyle(.insetGrouped)
            }
        }
        .themedScreen()
        .navigationTitle("Brand loyalty")
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do { programs = try await LoyaltyService.shared.programs(); error = nil }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }
}

struct LoyaltyBrandView: View {
    let brandID: String
    @State private var program: LoyaltyProgram?
    @State private var qr: LoyaltyMemberQR?
    @State private var error: String?

    var body: some View {
        Group {
            if let program {
                List {
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("\(program.balance?.points_balance ?? 0)")
                                .font(.system(size: 42, weight: .black, design: .rounded))
                                .foregroundStyle(TU.ember)
                            Text("\(program.balance?.tier_key.capitalized ?? "Bronze") tier · \(program.balance?.lifetime_points ?? 0) lifetime points")
                                .font(.interCaption).foregroundStyle(TU.textDim)
                        }
                        .padding(.vertical, 8)
                    }
                    .listRowBackground(TU.inkRaised)
                    Section {
                        NavigationLink("Show member card") { MemberCardView(brandID: brandID) }
                        ForEach(program.rewards) { reward in
                            HStack {
                                VStack(alignment: .leading) { Text(reward.title); Text("\(reward.points_cost) points").font(.interCaption).foregroundStyle(TU.ember) }
                                Spacer()
                                Button("Redeem") { Task { await redeem(reward) } }
                                    .buttonStyle(.borderedProminent).tint(TU.ember)
                            }
                        }
                    }
                    .listRowBackground(TU.inkRaised)
                }
                .listStyle(.insetGrouped)
            } else if let error {
                EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load loyalty", hint: error)
            } else {
                ProgressView()
            }
        }
        .themedScreen()
        .navigationTitle(program?.brand_name ?? "Loyalty")
        .task { await load() }
    }

    private func load() async {
        do { program = try await LoyaltyService.shared.program(brandID: brandID); error = nil }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }

    private func redeem(_ reward: LoyaltyReward) async {
        do { _ = try await LoyaltyService.shared.issueRedemption(brandID: brandID, rewardID: reward.id); await load() }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }
}

struct MemberCardView: View {
    let brandID: String
    @State private var qr: LoyaltyMemberQR?
    @State private var error: String?

    var body: some View {
        Group {
            if let qr {
                VStack(spacing: 18) {
                    Text("Show this code to staff").font(.interSubheadline).foregroundStyle(TU.textDim)
                    QRCodeView(content: qr.qr_payload)
                        .padding(20).background(.white, in: RoundedRectangle(cornerRadius: 18))
                        .frame(maxWidth: 320)
                    Text("Refreshes automatically").font(.interCaption).foregroundStyle(TU.textDim)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error {
                EmptyState(icon: "qrcode", title: "Member card unavailable", hint: error)
            } else { ProgressView() }
        }
        .themedContainer()
        .navigationTitle("Member card")
        .task { await refresh() }
    }

    private func refresh() async {
        do { qr = try await LoyaltyService.shared.memberQR(brandID: brandID); error = nil }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }
}
