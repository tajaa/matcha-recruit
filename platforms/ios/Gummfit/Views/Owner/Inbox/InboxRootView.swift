import SwiftUI

/// Inbox tab root — thread list, matching HomeView's top-level NavigationStack shape.
struct InboxRootView: View {
    let site: CappeSite

    var body: some View {
        NavigationStack {
            ThreadListView(site: site)
        }
    }
}
