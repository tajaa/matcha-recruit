import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @State private var isPasswordVisible = false
    @FocusState private var focusedField: Field?

    private enum Field { case email, password }

    private let ink = Color(red: 0.035, green: 0.071, blue: 0.075)
    private let paper = Color(red: 0.93, green: 0.95, blue: 0.88)
    private let paperDim = Color(red: 0.36, green: 0.41, blue: 0.38)

    private var canSubmit: Bool {
        !vm.loginEmail.isEmpty && !vm.loginPassword.isEmpty && !vm.isLoading
    }

    var body: some View {
        ZStack {
            ink
                .ignoresSafeArea()
                .overlay { backgroundArtwork }

            ScrollView(.vertical, showsIndicators: false) {
                pageContent
            }
            .safeAreaPadding(.bottom, 24)
        }
        .toolbar(.hidden, for: .navigationBar)
        .scrollDismissesKeyboard(.interactively)
        .preferredColorScheme(.dark)
    }

    private var pageContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            brandBar
                .padding(.top, 12)

            hero
                .padding(.top, 34)

            pulseCard
                .padding(.top, 28)
                .padding(.horizontal, 8)

            signInPanel
                .padding(.top, 32)

            footer
                .padding(.top, 22)
                .padding(.bottom, 36)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
    }

    private var backgroundArtwork: some View {
        ZStack {
            Circle()
                .stroke(GummfitTheme.accent.opacity(0.18), lineWidth: 1)
                .frame(width: 420, height: 420)
                .offset(x: 180, y: -350)

            Circle()
                .stroke(GummfitTheme.accent.opacity(0.09), lineWidth: 1)
                .frame(width: 570, height: 570)
                .offset(x: 180, y: -350)

            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [GummfitTheme.accent.opacity(0.10), .clear],
                        startPoint: .topTrailing,
                        endPoint: .bottomLeading
                    )
                )
                .frame(height: 340)
                .blur(radius: 30)
                .rotationEffect(.degrees(-12))
                .offset(y: -150)
        }
        .allowsHitTesting(false)
    }

    private var brandBar: some View {
        HStack(spacing: 11) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(GummfitTheme.accent)
                Text("g")
                    .font(.system(size: 27, weight: .black, design: .rounded))
                    .italic()
                    .foregroundStyle(ink)
            }
            .frame(width: 43, height: 43)

            VStack(alignment: .leading, spacing: 1) {
                Text("GUMMFIT")
                    .font(.system(size: 13, weight: .black, design: .rounded))
                    .tracking(2.4)
                Text("OPERATOR DESK")
                    .font(.system(size: 9, weight: .bold, design: .rounded))
                    .tracking(1.5)
                    .foregroundStyle(GummfitTheme.accent)
            }

            Spacer()

            Text("01 / 04")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(GummfitTheme.textDim)
        }
        .foregroundStyle(.white)
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("WELCOME BACK")
                .font(.system(size: 12, weight: .black, design: .rounded))
                .tracking(2.2)
                .foregroundStyle(GummfitTheme.accent)

            Text("Your business,\nin motion.")
                .font(.system(size: 46, weight: .black, design: .rounded))
                .tracking(-2.2)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)

            Text("One calm place for the work behind the storefront.")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(GummfitTheme.textDim)
        }
    }

    private var pulseCard: some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [GummfitTheme.surfaceRaised, GummfitTheme.surface],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .stroke(GummfitTheme.accent.opacity(0.24), lineWidth: 1)

            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("STORE PULSE")
                            .font(.system(size: 10, weight: .black, design: .rounded))
                            .tracking(1.7)
                            .foregroundStyle(GummfitTheme.accent)
                        Text("Everything looks good.")
                            .font(.system(size: 18, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                    }

                    Spacer()

                    HStack(spacing: 6) {
                        Circle()
                            .fill(GummfitTheme.accent)
                            .frame(width: 7, height: 7)
                        Text("LIVE")
                            .font(.system(size: 10, weight: .black, design: .rounded))
                            .foregroundStyle(GummfitTheme.accent)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(GummfitTheme.accent.opacity(0.12), in: Capsule())
                }

                HStack(alignment: .bottom, spacing: 18) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("24")
                            .font(.system(size: 42, weight: .black, design: .rounded))
                            .tracking(-2)
                            .foregroundStyle(.white)
                        Text("ORDERS TODAY")
                            .font(.system(size: 9, weight: .bold, design: .rounded))
                            .tracking(1.1)
                            .foregroundStyle(GummfitTheme.textDim)
                    }

                    HStack(alignment: .bottom, spacing: 6) {
                        ForEach(Array([20, 31, 24, 43, 36, 56, 47].enumerated()), id: \.offset) { item in
                            RoundedRectangle(cornerRadius: 3, style: .continuous)
                                .fill(item.offset == 6 ? GummfitTheme.accent : GummfitTheme.accent.opacity(0.38))
                                .frame(width: 9, height: CGFloat(item.element))
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .padding(.top, 24)
            }
            .padding(20)
        }
        .frame(height: 177)
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 25, style: .continuous))
        .rotationEffect(.degrees(-2.2))
        .shadow(color: GummfitTheme.accent.opacity(0.12), radius: 24, y: 14)
        .overlay(alignment: .bottomLeading) {
            Text("BUILT FOR THE BUSY ONES")
                .font(.system(size: 9, weight: .black, design: .rounded))
                .tracking(1.3)
                .foregroundStyle(ink)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(GummfitTheme.accent, in: Capsule())
                .offset(x: 18, y: 14)
        }
    }

    private var signInPanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("SIGN IN")
                        .font(.system(size: 12, weight: .black, design: .rounded))
                        .tracking(1.8)
                        .foregroundStyle(paperDim)
                    Text("Pick up where you left off.")
                        .font(.system(size: 21, weight: .black, design: .rounded))
                        .tracking(-0.5)
                        .foregroundStyle(ink)
                        .lineLimit(2)
                        .minimumScaleFactor(0.72)
                        .allowsTightening(true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .layoutPriority(1)

                Spacer(minLength: 8)

                Text("02")
                    .font(.system(size: 34, weight: .black, design: .rounded))
                    .tracking(-1.5)
                    .foregroundStyle(GummfitTheme.accentDeep.opacity(0.45))
                    .fixedSize()
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            ErrorBanner(message: vm.error)
                .frame(maxWidth: .infinity, alignment: .leading)

            VStack(spacing: 12) {
                field(
                    icon: "at",
                    title: "EMAIL ADDRESS",
                    placeholder: "you@business.com",
                    text: $vm.loginEmail,
                    contentType: .emailAddress,
                    keyboard: .emailAddress,
                    field: .email
                )

                passwordField
            }

            Button {
                focusedField = nil
                Task { await vm.login(appState: appState) }
            } label: {
                HStack {
                    Text(vm.isLoading ? "Signing in" : "Enter workspace")
                    Spacer()
                    if vm.isLoading {
                        ProgressView().tint(GummfitTheme.accent)
                    } else {
                        Image(systemName: "arrow.up.right")
                            .font(.headline.bold())
                    }
                }
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .padding(.horizontal, 18)
                .frame(maxWidth: .infinity)
                .frame(height: 57)
            }
            .foregroundStyle(canSubmit ? GummfitTheme.accent : GummfitTheme.accent.opacity(0.45))
            .background(ink, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .disabled(!canSubmit)
        }
        .padding(22)
        .frame(maxWidth: .infinity)
        .background(paper, in: RoundedRectangle(cornerRadius: 27, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 27, style: .continuous)
                .stroke(.white.opacity(0.7), lineWidth: 1)
        }
        .shadow(color: .black.opacity(0.32), radius: 24, y: 16)
    }

    private var passwordField: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("PASSWORD")
                .font(.system(size: 10, weight: .black, design: .rounded))
                .tracking(1.3)
                .foregroundStyle(paperDim)

            HStack(spacing: 11) {
                Image(systemName: "key.fill")
                    .foregroundStyle(paperDim)
                    .frame(width: 18)

                Group {
                    if isPasswordVisible {
                        TextField("Your password", text: $vm.loginPassword)
                    } else {
                        SecureField("Your password", text: $vm.loginPassword)
                    }
                }
                .textContentType(.password)
                .focused($focusedField, equals: .password)
                .submitLabel(.go)
                .onSubmit { submit() }

                Button {
                    isPasswordVisible.toggle()
                } label: {
                    Image(systemName: isPasswordVisible ? "eye.slash" : "eye")
                        .foregroundStyle(paperDim)
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(isPasswordVisible ? "Hide password" : "Show password")
            }
            .font(.body)
            .foregroundStyle(ink)
            .padding(.horizontal, 14)
            .frame(height: 49)
            .background(.white.opacity(0.58), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .stroke(focusedField == .password ? GummfitTheme.accentDeep : ink.opacity(0.13), lineWidth: focusedField == .password ? 1.5 : 1)
            }
        }
    }

    private func field(
        icon: String,
        title: String,
        placeholder: String,
        text: Binding<String>,
        contentType: UITextContentType,
        keyboard: UIKeyboardType,
        field: Field
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.system(size: 10, weight: .black, design: .rounded))
                .tracking(1.3)
                .foregroundStyle(paperDim)

            HStack(spacing: 11) {
                Image(systemName: icon)
                    .foregroundStyle(paperDim)
                    .frame(width: 18)
                TextField(placeholder, text: text)
                    .textContentType(contentType)
                    .keyboardType(keyboard)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focusedField, equals: field)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .password }
            }
            .foregroundStyle(ink)
            .padding(.horizontal, 14)
            .frame(height: 49)
            .background(.white.opacity(0.58), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .stroke(focusedField == field ? GummfitTheme.accentDeep : ink.opacity(0.13), lineWidth: focusedField == field ? 1.5 : 1)
            }
        }
    }

    private var footer: some View {
        VStack(spacing: 14) {
            NavigationLink {
                SignupView()
            } label: {
                HStack(spacing: 5) {
                    Text("New here?")
                        .foregroundStyle(GummfitTheme.textDim)
                    Text("Create an account")
                        .fontWeight(.bold)
                        .foregroundStyle(GummfitTheme.accent)
                }
            }

            HStack(spacing: 7) {
                Image(systemName: "lock.shield.fill")
                Text("Private, secure operator access")
            }
            .font(.system(size: 11, weight: .medium, design: .rounded))
            .foregroundStyle(GummfitTheme.textDim.opacity(0.75))
        }
        .frame(maxWidth: .infinity)
    }

    private func submit() {
        guard canSubmit else { return }
        focusedField = nil
        Task { await vm.login(appState: appState) }
    }
}
