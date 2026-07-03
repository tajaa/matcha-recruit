import SwiftUI

struct ActiveSessionView: View {
    @EnvironmentObject private var tutorViewModel: TutorViewModel

    var body: some View {
        VStack(spacing: 0) {
            // Header
            sessionHeader

            // Main content
            GeometryReader { geometry in
                HStack(spacing: 0) {
                    // Transcript area
                    transcriptArea
                        .frame(width: geometry.size.width * 0.65)

                    // Status panel
                    statusPanel
                        .frame(width: geometry.size.width * 0.35)
                }
            }

            // Controls
            controlsArea
        }
        .background(Color.black)
    }

    // MARK: - Session Header

    private var sessionHeader: some View {
        HStack {
            // Connection status & title
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Circle()
                        .fill(tutorViewModel.isConnected ? Color.green : Color.red)
                        .frame(width: 8, height: 8)
                        .overlay(
                            Circle()
                                .fill(Color.green.opacity(0.5))
                                .frame(width: 16, height: 16)
                                .opacity(tutorViewModel.isConnected ? 1 : 0)
                                .animation(.easeInOut(duration: 1).repeatForever(autoreverses: true), value: tutorViewModel.isConnected)
                        )

                    Text(tutorViewModel.selectedMode == .interviewPrep ? "INTERVIEW SIMULATION" : "LANGUAGE LAB")
                        .font(.system(size: 16, weight: .bold))
                        .tracking(2)
                        .foregroundColor(.white)
                }

                Text(subtitleText)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .tracking(2)
                    .foregroundColor(.gray)
                    .padding(.leading, 16)
            }

            Spacer()

            // Timer
            if let timeRemaining = tutorViewModel.sessionTimeRemaining {
                SessionTimerView(
                    timeRemaining: timeRemaining,
                    isWarning: tutorViewModel.isIdleWarning
                )
            }
        }
        .padding()
        .background(Color(white: 0.05))
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundColor(Color(white: 0.1)),
            alignment: .bottom
        )
    }

    private var subtitleText: String {
        if tutorViewModel.selectedMode == .interviewPrep {
            return "ROLE: \(tutorViewModel.selectedRole.displayName)"
        } else {
            return "TARGET: \(tutorViewModel.selectedLanguage.displayName)"
        }
    }

    // MARK: - Transcript Area

    private var transcriptArea: some View {
        VStack(spacing: 0) {
            if tutorViewModel.messages.isEmpty {
                emptyTranscriptView
            } else {
                TranscriptListView(messages: tutorViewModel.messages)
            }
        }
        .background(Color.black.opacity(0.4))
    }

    private var emptyTranscriptView: some View {
        VStack(spacing: 16) {
            Image(systemName: "mic.fill")
                .font(.system(size: 48))
                .foregroundColor(.gray.opacity(0.3))

            Text("WAITING FOR AUDIO INPUT...")
                .font(.system(size: 10, weight: .bold))
                .tracking(4)
                .foregroundColor(.gray.opacity(0.5))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Status Panel

    private var statusPanel: some View {
        VStack(spacing: 16) {
            // Session Status
            VStack(alignment: .leading, spacing: 16) {
                Text("SESSION STATUS")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.gray)
                    .padding(.bottom, 4)

                statusRow(label: "Connection", value: tutorViewModel.isConnected ? "Stable" : "Offline", isActive: tutorViewModel.isConnected)
                statusRow(label: "Audio Stream", value: tutorViewModel.isRecording ? "Active" : "Idle", isActive: tutorViewModel.isRecording)
                statusRow(label: "Transcript", value: "\(tutorViewModel.messages.count) Events", isActive: false)
            }
            .padding()
            .background(Color(white: 0.1))
            .overlay(
                Rectangle()
                    .stroke(Color(white: 0.15), lineWidth: 1)
            )

            // Tips
            VStack(alignment: .leading, spacing: 12) {
                Text("TIPS")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundColor(.gray)

                VStack(alignment: .leading, spacing: 8) {
                    tipText("Speak clearly and at a moderate pace.")
                    tipText("Wait for the AI to finish speaking.")
                    tipText("Use specific examples (STAR method).")
                }
            }
            .padding()
            .background(Color(white: 0.05))
            .overlay(
                Rectangle()
                    .stroke(Color(white: 0.1), lineWidth: 1)
            )

            Spacer()
        }
        .padding()
        .background(Color(white: 0.03))
        .overlay(
            Rectangle()
                .frame(width: 1)
                .foregroundColor(Color(white: 0.1)),
            alignment: .leading
        )
    }

    private func statusRow(label: String, value: String, isActive: Bool) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.gray)

            Spacer()

            Text(value.uppercased())
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(isActive ? (value == "Active" ? .red : .green) : .gray)
        }
    }

    private func tipText(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .foregroundColor(.gray)
            Text(text)
                .font(.system(size: 11))
                .foregroundColor(.gray)
        }
    }

    // MARK: - Controls Area

    private var controlsArea: some View {
        VStack(spacing: 0) {
            Rectangle()
                .frame(height: 1)
                .foregroundColor(Color(white: 0.1))

            HStack(spacing: 16) {
                if !tutorViewModel.isConnected {
                    // Connect button
                    Button(action: { tutorViewModel.connect() }) {
                        Text("INITIALIZE CONNECTION")
                            .font(.system(size: 12, weight: .bold))
                            .tracking(2)
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(Color.white)
                            .foregroundColor(.black)
                    }
                } else {
                    // Recording toggle
                    MicrophoneButton(
                        isRecording: tutorViewModel.isRecording,
                        action: {
                            Task {
                                await tutorViewModel.toggleRecording()
                            }
                        }
                    )

                    // End button
                    Button(action: { tutorViewModel.endSession() }) {
                        Text("END")
                            .font(.system(size: 12, weight: .bold))
                            .tracking(2)
                            .padding(.horizontal, 24)
                            .frame(height: 56)
                            .background(Color(white: 0.15))
                            .foregroundColor(.gray)
                            .overlay(
                                Rectangle()
                                    .stroke(Color(white: 0.25), lineWidth: 1)
                            )
                    }
                }
            }
            .padding()
            .background(Color(white: 0.1))
        }
    }
}

#Preview {
    ActiveSessionView()
        .environmentObject(TutorViewModel())
}
