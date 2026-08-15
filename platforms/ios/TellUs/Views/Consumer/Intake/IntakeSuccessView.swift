import SwiftUI

struct IntakeSuccessView: View {
    let result: FeedbackSubmitResponse
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill")
                .font(.custom("Inter-Regular", size: 56))
                .foregroundStyle(.green)

            Text("Thanks for the feedback!").font(.interTitle2.bold())

            if result.points_awarded > 0 {
                PointsPill(points: result.points_awarded)
            }

            if result.reward_pending {
                Text("Your points are pending brand approval.")
                    .font(.interFootnote).foregroundStyle(.secondary)
            }
            if result.public_review, let publishAt = result.publish_at {
                Text("Your review publishes \(Formatters.relativeString(from: publishAt)) — a short hold before it goes live.")
                    .font(.interFootnote).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Button("Done") { dismiss() }
                .frame(maxWidth: .infinity).padding()
                .background(.tint, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
        }
        .padding()
        .navigationBarBackButtonHidden(true)
    }
}
