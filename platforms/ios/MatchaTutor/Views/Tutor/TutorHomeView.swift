import SwiftUI

struct TutorHomeView: View {
    @EnvironmentObject private var authViewModel: AuthViewModel
    @StateObject private var tutorViewModel = TutorViewModel()

    private var isCandidate: Bool {
        authViewModel.currentUser?.role == .candidate
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                Group {
                    switch tutorViewModel.sessionState {
                    case .idle, .error:
                        modeSelectionView
                    case .starting, .connecting:
                        loadingView
                    case .connected, .recording:
                        ActiveSessionView()
                            .environmentObject(tutorViewModel)
                    case .completed:
                        completedView
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if tutorViewModel.sessionState == .idle {
                        Button(action: { authViewModel.logout() }) {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                                .foregroundColor(.gray)
                        }
                    }
                }

                ToolbarItem(placement: .principal) {
                    Text("MATCHA TUTOR")
                        .font(.system(size: 12, weight: .bold))
                        .tracking(4)
                        .foregroundColor(.white)
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    if isCandidate {
                        tokenBadge
                    }
                }
            }
        }
    }

    // MARK: - Mode Selection

    private var modeSelectionView: some View {
        ScrollView {
            VStack(spacing: 32) {
                // Header
                VStack(spacing: 8) {
                    Text(isCandidate ? "INTERVIEW PREP" : "TUTOR")
                        .font(.system(size: 36, weight: .black))
                        .tracking(2)
                        .foregroundColor(.white)

                    Text(isCandidate ? "AI-Powered Role Simulation" : "Language & Interview Practice")
                        .font(.system(size: 11, weight: .medium))
                        .tracking(3)
                        .foregroundColor(.gray)
                        .textCase(.uppercase)
                }
                .padding(.top, 20)

                // Error message
                if case .error(let message) = tutorViewModel.sessionState {
                    errorBanner(message)
                }

                // Token warning for candidates
                if isCandidate && authViewModel.interviewPrepTokens == 0 {
                    tokenWarningBanner
                }

                // Interview Prep Card
                interviewPrepCard

                // Language Test Card (admin only)
                if !isCandidate {
                    languageTestCard
                }

                Spacer(minLength: 50)
            }
            .padding(.horizontal, 24)
        }
    }

    // MARK: - Interview Prep Card

    private var interviewPrepCard: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Header
            HStack {
                ZStack {
                    Rectangle()
                        .fill(Color.white)
                        .frame(width: 48, height: 48)

                    Image(systemName: "person.2.fill")
                        .font(.system(size: 20))
                        .foregroundColor(.black)
                }

                Spacer()

                Image(systemName: "person.2.fill")
                    .font(.system(size: 80))
                    .foregroundColor(.white.opacity(0.05))
            }

            // Title
            VStack(alignment: .leading, spacing: 4) {
                Text("ROLE SIMULATION")
                    .font(.system(size: 20, weight: .bold))
                    .tracking(1)
                    .foregroundColor(.white)

                Text("Practice role-specific interview questions with AI feedback")
                    .font(.system(size: 13))
                    .foregroundColor(.gray)
                    .lineLimit(2)
            }

            // Role Selection
            VStack(alignment: .leading, spacing: 8) {
                Text("TARGET ROLE")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.gray)

                let availableRoles = isCandidate
                    ? InterviewRole.allCases.filter { authViewModel.allowedInterviewRoles.contains($0.rawValue) }
                    : InterviewRole.allCases

                if availableRoles.isEmpty {
                    Text("No roles assigned")
                        .font(.system(size: 12))
                        .foregroundColor(.gray)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .overlay(
                            Rectangle()
                                .stroke(style: StrokeStyle(lineWidth: 1, dash: [4]))
                                .foregroundColor(Color(white: 0.2))
                        )
                } else {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(availableRoles, id: \.self) { role in
                            RoleButton(
                                role: role,
                                isSelected: tutorViewModel.selectedRole == role,
                                action: { tutorViewModel.selectedRole = role }
                            )
                        }
                    }
                }
            }

            // Duration Selection
            VStack(alignment: .leading, spacing: 8) {
                Text("DURATION")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.gray)

                HStack(spacing: 8) {
                    ForEach([SessionDuration.medium, SessionDuration.long], id: \.self) { duration in
                        DurationButton(
                            duration: duration,
                            isSelected: tutorViewModel.selectedDuration == duration,
                            action: { tutorViewModel.selectedDuration = duration }
                        )
                    }
                }
            }

            // Start Button
            Button(action: startInterviewSession) {
                Text("START SIMULATION")
                    .font(.system(size: 14, weight: .bold))
                    .tracking(2)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(canStartInterview ? Color.white : Color(white: 0.2))
                    .foregroundColor(canStartInterview ? .black : .gray)
            }
            .disabled(!canStartInterview)

            if isCandidate {
                Text("Cost: 1 Token")
                    .font(.system(size: 10, weight: .medium))
                    .tracking(2)
                    .foregroundColor(.gray)
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(24)
        .background(Color(white: 0.05))
        .overlay(
            Rectangle()
                .stroke(Color(white: 0.15), lineWidth: 1)
        )
    }

    private var canStartInterview: Bool {
        if isCandidate {
            let availableRoles = InterviewRole.allCases.filter { authViewModel.allowedInterviewRoles.contains($0.rawValue) }
            return authViewModel.interviewPrepTokens > 0 && !availableRoles.isEmpty
        }
        return true
    }

    // MARK: - Language Test Card

    private var languageTestCard: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Header
            HStack {
                ZStack {
                    Rectangle()
                        .fill(Color(white: 0.15))
                        .frame(width: 48, height: 48)
                        .overlay(
                            Rectangle()
                                .stroke(Color(white: 0.25), lineWidth: 1)
                        )

                    Image(systemName: "globe")
                        .font(.system(size: 20))
                        .foregroundColor(.gray)
                }

                Spacer()
            }

            // Title
            VStack(alignment: .leading, spacing: 4) {
                Text("LANGUAGE LAB")
                    .font(.system(size: 20, weight: .bold))
                    .tracking(1)
                    .foregroundColor(.white)

                Text("Test fluency and grammar through natural conversation")
                    .font(.system(size: 13))
                    .foregroundColor(.gray)
                    .lineLimit(2)
            }

            // Language Selection
            VStack(alignment: .leading, spacing: 8) {
                Text("LANGUAGE")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.gray)

                HStack(spacing: 8) {
                    ForEach(TutorLanguage.allCases, id: \.self) { language in
                        LanguageButton(
                            language: language,
                            isSelected: tutorViewModel.selectedLanguage == language,
                            action: { tutorViewModel.selectedLanguage = language }
                        )
                    }
                }
            }

            // Duration Selection
            VStack(alignment: .leading, spacing: 8) {
                Text("DURATION")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.gray)

                HStack(spacing: 8) {
                    ForEach([SessionDuration.short, SessionDuration.long], id: \.self) { duration in
                        DurationButton(
                            duration: duration,
                            isSelected: tutorViewModel.selectedDuration == duration,
                            style: .secondary,
                            action: { tutorViewModel.selectedDuration = duration }
                        )
                    }
                }
            }

            // Start Button
            Button(action: startLanguageSession) {
                HStack(spacing: 8) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 12))
                    Text("START PRACTICE")
                        .font(.system(size: 14, weight: .bold))
                        .tracking(2)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 56)
                .background(Color.clear)
                .foregroundColor(.white)
                .overlay(
                    Rectangle()
                        .stroke(Color(white: 0.3), lineWidth: 1)
                )
            }
        }
        .padding(24)
        .background(Color(white: 0.03))
        .overlay(
            Rectangle()
                .stroke(Color(white: 0.1), lineWidth: 1)
        )
    }

    // MARK: - Loading View

    private var loadingView: some View {
        VStack(spacing: 24) {
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                .scaleEffect(1.5)

            Text("INITIALIZING...")
                .font(.system(size: 12, weight: .bold))
                .tracking(4)
                .foregroundColor(.gray)
        }
    }

    // MARK: - Completed View

    private var completedView: some View {
        VStack(spacing: 32) {
            // Success Icon
            ZStack {
                Circle()
                    .fill(Color.green.opacity(0.2))
                    .frame(width: 80, height: 80)

                Circle()
                    .stroke(Color.green.opacity(0.5), lineWidth: 1)
                    .frame(width: 80, height: 80)

                Image(systemName: "checkmark")
                    .font(.system(size: 36, weight: .semibold))
                    .foregroundColor(.green)
            }

            VStack(spacing: 8) {
                Text("SESSION COMPLETE")
                    .font(.system(size: 28, weight: .black))
                    .tracking(2)
                    .foregroundColor(.white)

                Text("Analysis in progress...")
                    .font(.system(size: 12, weight: .medium))
                    .tracking(2)
                    .foregroundColor(.gray)
            }

            // Session Summary
            VStack(spacing: 16) {
                Text(tutorViewModel.selectedMode == .interviewPrep
                     ? "\(tutorViewModel.selectedRole.displayName) Simulation"
                     : "Language Practice")
                    .font(.system(size: 16, weight: .bold))
                    .tracking(1)
                    .foregroundColor(.white)

                Text(tutorViewModel.selectedMode == .interviewPrep
                     ? "Your responses have been recorded. Detailed feedback is being generated."
                     : "Great job practicing \(tutorViewModel.selectedLanguage.displayName)!")
                    .font(.system(size: 13))
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .padding(24)
            .frame(maxWidth: .infinity)
            .background(Color(white: 0.1))
            .overlay(
                Rectangle()
                    .stroke(Color(white: 0.2), lineWidth: 1)
            )
            .padding(.horizontal, 24)

            // Actions
            VStack(spacing: 12) {
                Button(action: { tutorViewModel.resetSession() }) {
                    Text("START NEW SESSION")
                        .font(.system(size: 14, weight: .bold))
                        .tracking(2)
                        .frame(maxWidth: .infinity)
                        .frame(height: 56)
                        .background(Color.white)
                        .foregroundColor(.black)
                }
            }
            .padding(.horizontal, 24)
        }
    }

    // MARK: - Helper Views

    private var tokenBadge: some View {
        HStack(spacing: 6) {
            Image(systemName: "star.fill")
                .font(.system(size: 12))
                .foregroundColor(.yellow)

            Text("\(authViewModel.interviewPrepTokens)")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundColor(authViewModel.interviewPrepTokens > 0 ? .white : .red)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color(white: 0.1))
        .overlay(
            Rectangle()
                .stroke(Color(white: 0.2), lineWidth: 1)
        )
    }

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: 12) {
            Circle()
                .fill(Color.red)
                .frame(width: 8, height: 8)

            Text(message)
                .font(.system(size: 12, weight: .medium, design: .monospaced))
                .foregroundColor(.red)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.red.opacity(0.1))
        .overlay(
            Rectangle()
                .stroke(Color.red.opacity(0.3), lineWidth: 1)
        )
    }

    private var tokenWarningBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "clock.fill")
                    .foregroundColor(.yellow)
                Text("INSUFFICIENT TOKENS")
                    .font(.system(size: 12, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.yellow)
            }

            Text("You have exhausted your interview preparation tokens. Please contact your administrator.")
                .font(.system(size: 11, weight: .medium, design: .monospaced))
                .foregroundColor(.yellow.opacity(0.8))
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.yellow.opacity(0.1))
        .overlay(
            Rectangle()
                .stroke(Color.yellow.opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Actions

    private func startInterviewSession() {
        tutorViewModel.selectedMode = .interviewPrep
        Task {
            await tutorViewModel.startSession()
            if isCandidate {
                await authViewModel.refreshUser()
            }
        }
    }

    private func startLanguageSession() {
        tutorViewModel.selectedMode = .languageTest
        Task {
            await tutorViewModel.startSession()
        }
    }
}

// MARK: - Supporting Views

struct RoleButton: View {
    let role: InterviewRole
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(role.displayName)
                .font(.system(size: 11, weight: .bold))
                .tracking(1)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(isSelected ? Color.white : Color(white: 0.1))
                .foregroundColor(isSelected ? .black : .gray)
                .overlay(
                    Rectangle()
                        .stroke(isSelected ? Color.white : Color(white: 0.2), lineWidth: 1)
                )
        }
    }
}

struct DurationButton: View {
    let duration: SessionDuration
    let isSelected: Bool
    var style: ButtonStyle = .primary
    let action: () -> Void

    enum ButtonStyle {
        case primary, secondary
    }

    var body: some View {
        Button(action: action) {
            Text(duration.displayName.uppercased())
                .font(.system(size: 11, weight: .bold))
                .tracking(2)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(backgroundColor)
                .foregroundColor(foregroundColor)
                .overlay(
                    Rectangle()
                        .stroke(borderColor, lineWidth: 1)
                )
        }
    }

    private var backgroundColor: Color {
        switch style {
        case .primary:
            return isSelected ? Color.white : Color(white: 0.1)
        case .secondary:
            return isSelected ? Color(white: 0.15) : Color(white: 0.05)
        }
    }

    private var foregroundColor: Color {
        switch style {
        case .primary:
            return isSelected ? .black : .gray
        case .secondary:
            return isSelected ? .white : .gray
        }
    }

    private var borderColor: Color {
        switch style {
        case .primary:
            return isSelected ? Color.white : Color(white: 0.2)
        case .secondary:
            return isSelected ? Color(white: 0.3) : Color(white: 0.15)
        }
    }
}

struct LanguageButton: View {
    let language: TutorLanguage
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(language.displayName.uppercased())
                .font(.system(size: 11, weight: .bold))
                .tracking(2)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(isSelected ? Color(white: 0.15) : Color(white: 0.05))
                .foregroundColor(isSelected ? .white : .gray)
                .overlay(
                    Rectangle()
                        .stroke(isSelected ? Color(white: 0.3) : Color(white: 0.15), lineWidth: 1)
                )
        }
    }
}

#Preview {
    TutorHomeView()
        .environmentObject(AuthViewModel())
}
