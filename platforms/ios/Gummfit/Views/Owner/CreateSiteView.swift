import SwiftUI

/// First-site (blocking, no dismiss) or additional-site (sheet, dismissable)
/// — `isFirstSite` only changes chrome, not behavior. No page editor (plan
/// §"No page editor") — creation always yields a blank site; editing content
/// stays on web.
struct CreateSiteView: View {
    var isFirstSite: Bool = false

    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var vm = SitesViewModel()
    @FocusState private var nameFocused: Bool

    var body: some View {
        VStack(spacing: 20) {
            ErrorBanner(message: vm.error)

            VStack(spacing: 6) {
                Text(isFirstSite ? "Create your site" : "New site")
                    .font(.title2.bold())
                if isFirstSite {
                    Text("Give your business a name to get started. You can change it later.")
                        .font(.subheadline)
                        .foregroundStyle(GummfitTheme.textDim)
                        .multilineTextAlignment(.center)
                }
            }

            TextField("Business name", text: $vm.name)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .focused($nameFocused)
                .submitLabel(.go)
                .onSubmit(submit)

            Button(action: submit) {
                if vm.isLoading {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    Text("Create").frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!vm.canSubmit)

            if !isFirstSite {
                Button("Cancel") { dismiss() }
                    .disabled(vm.isLoading)
            }

            Spacer()
        }
        .padding()
        .background(Color(GummfitTheme.background).ignoresSafeArea())
        .navigationBarBackButtonHidden(isFirstSite)
        .task { nameFocused = true }
    }

    private func submit() {
        guard vm.canSubmit else { return }
        Task {
            await vm.create(appState: appState)
            // vm.error is nil only on success (withLoad clears it up front
            // and only sets it on a caught error) — dismiss the sheet rather
            // than making the user tap again. The first-site flow doesn't
            // dismiss; AppState.sites becoming non-empty switches RootView
            // away from this screen entirely.
            if !isFirstSite && vm.error == nil {
                dismiss()
            }
        }
    }
}
