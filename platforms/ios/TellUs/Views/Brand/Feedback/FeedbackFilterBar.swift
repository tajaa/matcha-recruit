import SwiftUI

struct FeedbackFilterBar: View {
    @Bindable var vm: FeedbackListViewModel

    var body: some View {
        HStack {
            Menu {
                Button("All statuses") { vm.statusFilter = nil; Task { await vm.load(reset: true) } }
                ForEach(ReportStatus.allCases, id: \.self) { status in
                    Button(status.rawValue.capitalized) { vm.statusFilter = status; Task { await vm.load(reset: true) } }
                }
            } label: {
                Label(vm.statusFilter?.rawValue.capitalized ?? "Status", systemImage: "line.3.horizontal.decrease.circle")
            }

            Spacer()

            Menu {
                Button("All sentiments") { vm.sentimentFilter = nil; Task { await vm.load(reset: true) } }
                ForEach(Sentiment.allCases, id: \.self) { sentiment in
                    Button(sentiment.rawValue.capitalized) { vm.sentimentFilter = sentiment; Task { await vm.load(reset: true) } }
                }
            } label: {
                Label(vm.sentimentFilter?.rawValue.capitalized ?? "Sentiment", systemImage: "face.smiling")
            }
        }
        .font(.footnote)
        .padding(.horizontal)
        .padding(.vertical, 8)
    }
}
