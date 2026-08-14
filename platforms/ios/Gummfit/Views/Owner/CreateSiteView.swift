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
                    .gummfitPageTitle()
                if isFirstSite {
                    Text("Give your business a name to get started. You can change it later.")
                        .font(.subheadline)
                        .foregroundStyle(GummfitTheme.textDim)
                        .multilineTextAlignment(.center)
                }
            }

            TextField("Business name", text: $vm.name)
                .textFieldStyle(GummfitTextFieldStyle())
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
            .buttonStyle(.gummfitPrimary)
            .disabled(!vm.canSubmit)

            if isFirstSite {
                Button("Sign out", role: .destructive) { appState.didLogout() }
                    .disabled(vm.isLoading)
            } else {
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
            // `created` is explicit success, not "error == nil" — withLoad
            // also returns with a nil error on cancellation, which would
            // otherwise dismiss the sheet with no site actually created. The
            // first-site flow doesn't dismiss; AppState.sites becoming
            // non-empty switches RootView away from this screen entirely.
            let created = await vm.create(appState: appState)
            if !isFirstSite && created {
                dismiss()
            }
        }
    }
}
