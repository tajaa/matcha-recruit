import SwiftUI

struct IntakeLoaderView: View {
    let token: String
    @State private var vm: IntakeViewModel

    init(token: String) {
        self.token = token
        _vm = State(initialValue: IntakeViewModel(token: token))
    }

    var body: some View {
        Group {
            if let error = vm.loadError {
                EmptyState(icon: "exclamationmark.triangle", title: "Link unavailable", hint: error)
            } else if vm.config == nil {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                IntakeFormView(vm: vm)
            }
        }
        .navigationTitle("Leave feedback")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.loadConfig() }
    }
}
