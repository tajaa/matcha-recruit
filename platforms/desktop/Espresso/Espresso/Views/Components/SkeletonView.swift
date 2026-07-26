import SwiftUI

/// Reusable shimmer placeholders shown during a *cold* load (no cached data
/// yet). Warm re-entry keeps the real content visible and never shows these —
/// the detail views gate them on `data == nil && isLoading`.

/// Animated shimmer sweep applied over placeholder content.
struct ShimmerModifier: ViewModifier {
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .overlay(
                GeometryReader { geo in
                    LinearGradient(
                        colors: [.clear, Color.white.opacity(0.16), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: geo.size.width * 0.6)
                    .offset(x: phase * geo.size.width * 1.6)
                    .allowsHitTesting(false)
                }
            )
            .clipped()
            .onAppear {
                withAnimation(.linear(duration: 1.2).repeatForever(autoreverses: false)) {
                    phase = 1
                }
            }
    }
}

extension View {
    func shimmer() -> some View { modifier(ShimmerModifier()) }
}

/// A single rounded placeholder bar. With no explicit width it fills the
/// available horizontal space (left-aligned).
struct SkeletonBar: View {
    var width: CGFloat? = nil
    var height: CGFloat = 12
    @Environment(AppState.self) private var appState

    var body: some View {
        RoundedRectangle(cornerRadius: 5)
            .fill(appState.themeText.opacity(0.08))
            .frame(width: width, height: height)
            .frame(maxWidth: width == nil ? .infinity : nil, alignment: .leading)
    }
}

/// Skeleton for a chat / thread surface: a column of message-row placeholders.
struct ChatSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(0..<6, id: \.self) { i in
                HStack(alignment: .top, spacing: 10) {
                    Circle()
                        .fill(Color.secondary.opacity(0.12))
                        .frame(width: 26, height: 26)
                    VStack(alignment: .leading, spacing: 6) {
                        SkeletonBar(width: 110, height: 10)
                        SkeletonBar(width: i.isMultiple(of: 2) ? 260 : 190, height: 12)
                        if i.isMultiple(of: 3) {
                            SkeletonBar(width: 210, height: 12)
                        }
                    }
                    Spacer()
                }
            }
            Spacer()
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .shimmer()
    }
}

/// Skeleton for a project detail surface: a header bar, a left list column, and
/// a body of text lines.
struct ProjectDetailSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                SkeletonBar(width: 20, height: 20)
                SkeletonBar(width: 180, height: 16)
                Spacer()
                SkeletonBar(width: 80, height: 22)
            }
            .padding(16)
            Divider().opacity(0.1)
            HStack(alignment: .top, spacing: 0) {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(0..<6, id: \.self) { _ in SkeletonBar(height: 12) }
                    Spacer()
                }
                .frame(width: 220)
                .padding(16)
                Divider().opacity(0.1)
                VStack(alignment: .leading, spacing: 14) {
                    SkeletonBar(width: 260, height: 20)
                    ForEach(0..<8, id: \.self) { i in
                        SkeletonBar(width: i.isMultiple(of: 2) ? nil : 320, height: 12)
                    }
                    Spacer()
                }
                .padding(20)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .shimmer()
    }
}
