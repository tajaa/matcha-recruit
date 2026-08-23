import SwiftUI

struct WelcomeView: View {
    var body: some View {
        ZStack {
            EmberBackground()

            ScrollView {
                VStack(spacing: 0) {
                    brandHeader
                        .riseIn(0)

                    hero
                        .riseIn(1)
                        .padding(.top, 42)

                    WelcomeReceiptView()
                        .riseIn(2)
                        .padding(.top, 30)

                    valueSteps
                        .riseIn(3)
                        .padding(.top, 28)

                    actions
                        .riseIn(4)
                        .padding(.top, 30)

                    Text("Free for consumers. Built for honest feedback.")
                        .font(.interCaption)
                        .foregroundStyle(TU.textDim)
                        .multilineTextAlignment(.center)
                        .padding(.top, 18)
                        .padding(.bottom, 28)
                }
                .frame(maxWidth: 520)
                .padding(.horizontal, 24)
                .padding(.top, 18)
                .padding(.bottom, 12)
                .frame(maxWidth: .infinity)
            }
            .scrollIndicators(.hidden)
            .scrollDismissesKeyboard(.interactively)
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationBarBackButtonHidden(true)
    }

    private var brandHeader: some View {
        HStack(spacing: 10) {
            BrandMark(size: 29)

            VStack(alignment: .leading, spacing: 2) {
                Text("BEETLEJUSE")
                    .font(TU.eyebrow(12).weight(.bold))
                    .tracking(1.7)
                    .foregroundStyle(.white)

                Text("FEEDBACK / REWARDS")
                    .font(TU.eyebrow(9))
                    .tracking(1.1)
                    .foregroundStyle(TU.textDim)
            }

            Spacer()

            Text("FREE TO JOIN")
                .font(TU.eyebrow(9).weight(.semibold))
                .tracking(0.7)
                .foregroundStyle(TU.emberHot)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(TU.ember.opacity(0.10), in: Capsule())
                .overlay(Capsule().strokeBorder(TU.ember.opacity(0.28), lineWidth: 1))
        }
    }

    private var hero: some View {
        VStack(spacing: 14) {
            Text("LOCAL FEEDBACK, REAL REWARDS")
                .font(TU.eyebrow(10).weight(.semibold))
                .tracking(1.8)
                .foregroundStyle(TU.emberHot)

            VStack(spacing: 0) {
                Text("Your voice")
                    .foregroundStyle(.white)
                Text("has value.")
                    .foregroundStyle(TU.emberHot)
            }
            .font(.interLargeTitle.weight(.bold))
            .tracking(-1.4)
            .multilineTextAlignment(.center)

            Text("Tell businesses what is working, what is not, and what would bring you back. Earn points for making the places around you better.")
                .font(.interSubheadline)
                .foregroundStyle(TU.textDim)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var valueSteps: some View {
        HStack(spacing: 8) {
            WelcomeStep(icon: "qrcode.viewfinder", label: "SCAN", detail: "A place")
            WelcomeStep(icon: "text.bubble.fill", label: "SHARE", detail: "Your take")
            WelcomeStep(icon: "star.fill", label: "EARN", detail: "Real perks")
        }
    }

    private var actions: some View {
        VStack(spacing: 12) {
            NavigationLink {
                SignupView(initialAccountType: .consumer)
            } label: {
                HStack(spacing: 8) {
                    Text("Start earning")
                    Image(systemName: "arrow.right")
                        .font(.system(size: 14, weight: .bold))
                }
            }
            .buttonStyle(EmberButtonStyle())

            NavigationLink {
                LoginView()
            } label: {
                Text("I already have an account")
            }
            .buttonStyle(GhostButtonStyle())

            NavigationLink {
                SignupView(initialAccountType: .brand)
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "storefront")
                    Text("I run a business")
                    Image(systemName: "arrow.up.right")
                        .font(.system(size: 11, weight: .semibold))
                }
                .font(.interFootnote.weight(.medium))
                .foregroundStyle(TU.textDim)
            }
            .padding(.top, 3)
        }
    }
}

private struct WelcomeStep: View {
    let icon: String
    let label: String
    let detail: String

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(TU.emberHot)
                .frame(height: 20)

            Text(label)
                .font(TU.eyebrow(9).weight(.bold))
                .tracking(1.1)
                .foregroundStyle(.white)

            Text(detail)
                .font(.interCaption2)
                .foregroundStyle(TU.textDim)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 13)
        .glassCard(radius: 15, strokeOpacity: 0.8)
    }
}

private struct WelcomeReceiptView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isShown = false

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(TU.ember.opacity(0.10))
                .frame(maxWidth: .infinity)
                .frame(height: 238)
                .rotationEffect(.degrees(4))
                .offset(x: 7, y: 8)

            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    HStack(spacing: 9) {
                        Image(systemName: "cup.and.saucer.fill")
                            .font(.system(size: 15, weight: .medium))
                            .frame(width: 29, height: 29)
                            .background(Color.black.opacity(0.08), in: RoundedRectangle(cornerRadius: 8, style: .continuous))

                        Text("Corner Coffee Co.")
                            .font(.interSubheadline.weight(.semibold))
                    }

                    Spacer()

                    Text("APPROVED")
                        .font(TU.eyebrow(8).weight(.bold))
                        .tracking(0.6)
                        .foregroundStyle(Color(red: 0.12, green: 0.48, blue: 0.30))
                }

                Rectangle()
                    .fill(Color.black.opacity(0.12))
                    .frame(height: 1)
                    .padding(.top, 14)

                HStack(spacing: 6) {
                    ReceiptChip(title: "POSITIVE", icon: "face.smiling.fill")
                    ReceiptChip(title: "SERVICE", icon: "text.bubble.fill")
                    ReceiptChip(title: "PHOTO", icon: "camera.fill")
                }
                .padding(.top, 13)

                Text("\"The new oat latte is great. Fix the sticky door and this is my new favorite stop.\"")
                    .font(.interFootnote)
                    .foregroundStyle(Color.black.opacity(0.70))
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 13)

                HStack {
                    Text("REWARD CREDITED")
                        .font(TU.eyebrow(9).weight(.medium))
                        .tracking(0.8)
                        .foregroundStyle(Color.black.opacity(0.55))

                    Spacer()

                    HStack(spacing: 5) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 12, weight: .bold))
                        Text("+185 PTS")
                            .font(TU.eyebrow(14).weight(.bold))
                    }
                    .foregroundStyle(TU.emberDeep)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 11)
                .background(Color.black.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .padding(.top, 14)
            }
            .padding(18)
            .foregroundStyle(Color.black.opacity(0.82))
            .background(
                LinearGradient(
                    colors: [Color(red: 0.98, green: 0.94, blue: 0.85), Color(red: 0.91, green: 0.84, blue: 0.70)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 20, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.30), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.35), radius: 24, y: 14)
            .offset(y: isShown ? 0 : 14)
            .opacity(isShown ? 1 : 0)

            HStack(spacing: 6) {
                Image(systemName: "flame.fill")
                    .foregroundStyle(TU.emberHot)
                Text("4 DAY STREAK")
                    .font(TU.eyebrow(9).weight(.bold))
                    .tracking(0.7)
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 8)
            .background(TU.inkRaised, in: Capsule())
            .overlay(Capsule().strokeBorder(TU.hairline, lineWidth: 1))
            .shadow(color: .black.opacity(0.25), radius: 8, y: 5)
            .offset(x: -8, y: 12)
            .opacity(isShown ? 1 : 0)
        }
        .frame(height: 270)
        .onAppear {
            guard !reduceMotion else {
                isShown = true
                return
            }
            withAnimation(.spring(response: 0.65, dampingFraction: 0.78).delay(0.08)) {
                isShown = true
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Sample approved feedback from Corner Coffee Co. Reward credited: 185 points. Four day streak.")
    }
}

private struct ReceiptChip: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(TU.eyebrow(8).weight(.semibold))
            .lineLimit(1)
            .minimumScaleFactor(0.75)
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(Color.black.opacity(0.08), in: Capsule())
    }
}
