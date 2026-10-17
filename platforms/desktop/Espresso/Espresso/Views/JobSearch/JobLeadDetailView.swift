import SwiftUI
import AppKit

/// One job: pay with the text it came from, how to approach it, and the
/// drafts (outreach, answers to the application's own questions, cover
/// letter). Every draft has Copy, and the first message can go to the
/// person's Gmail drafts ("Draft email"); nothing here sends or submits.
struct JobLeadDetailView: View {
    @Environment(AppState.self) private var appState
    let vm: JobSearchViewModel
    let onClose: () -> Void
    @State private var notes = ""
    @State private var notesLeadId: String?
    @State private var copied: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Close")
            }
            .padding(.horizontal, 14).padding(.top, 10)
            if let lead = vm.lead {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        heading(lead)
                        paySection(lead)
                        approachSection(lead)
                        notesSection(lead)
                        if !lead.description.isEmpty { descriptionSection(lead.description) }
                    }
                    .padding(.horizontal, 18).padding(.bottom, 24)
                }
                .onAppear { syncNotes(lead) }
                .onChange(of: lead.summary.id) { _, _ in syncNotes(lead) }
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(appState.themeBg.opacity(0.4))
    }

    private func syncNotes(_ lead: JobLeadDetail) {
        guard notesLeadId != lead.summary.id else { return }
        notesLeadId = lead.summary.id
        notes = lead.notes
    }

    // MARK: Heading

    private func heading(_ lead: JobLeadDetail) -> some View {
        let job = lead.summary
        return VStack(alignment: .leading, spacing: 6) {
            Text(job.title)
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(appState.themeText)
                .textSelection(.enabled)
            Text([job.company, job.location, job.remote == true ? "Remote" : nil, job.postedText]
                .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " \u{00B7} "))
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
            if !lead.fitReasons.isEmpty || job.fitScore != nil {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("Fit \(JobSearchViewModel.fitText(job.fitScore))")
                        .font(.system(size: 10, weight: .semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(appState.themeAccent.opacity(0.12)))
                        .fixedSize()
                    Text(lead.fitReasons.joined(separator: " \u{00B7} "))
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if job.isIrrelevant, let reason = lead.screenReason, !reason.isEmpty {
                Text("Screened out: \(reason)").font(.system(size: 11)).foregroundColor(.orange)
            }
            HStack(spacing: 8) {
                if let url = JobSearchViewModel.webURL(job.applyUrl ?? job.sourceUrl) {
                    Button { NSWorkspace.shared.open(url) } label: {
                        Label("Open posting", systemImage: "arrow.up.right.square")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                }
                emailButton(lead)
            }
            .font(.system(size: 11))
            .padding(.top, 2)
            if vm.emailDraftGoneLeadId == job.id {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "envelope.open").foregroundColor(.orange)
                    Text("That draft isn't in your Gmail drafts any more, so it was sent or deleted there. Draft email makes a new one if you still want it.")
                        .foregroundColor(appState.themeTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(.system(size: 11))
            }
            if vm.emailNotConnected {
                HStack(spacing: 6) {
                    Image(systemName: "envelope.badge").foregroundColor(.orange)
                    Text("Connect Gmail in Email first, then Draft email again.")
                        .foregroundColor(appState.themeTextSecondary)
                    Button("Open Email") { appState.openEmailDrafts() }
                        .buttonStyle(.plain)
                        .foregroundColor(appState.themeAccent)
                }
                .font(.system(size: 11))
            }
            HStack(spacing: 8) {
                Menu {
                    Button("Saved") { Task { await vm.setState("saved", leadId: job.id) } }
                    Button("Applied") { Task { await vm.setState("applied", leadId: job.id) } }
                    Button("Dismiss") { Task { await vm.setState("dismissed", leadId: job.id) } }
                    if job.userState != "new" {
                        Divider()
                        Button("Clear") { Task { await vm.setState("new", leadId: job.id) } }
                    }
                } label: {
                    Text(job.userState == "new" ? "Mark…" : job.userState.capitalized)
                }
                .fixedSize()
                .disabled(vm.busy)
                if appState.assistantEnabled {
                    Button {
                        if let search = vm.selectedSearchId {
                            appState.workOnJobSearch(searchId: search, jobId: job.id,
                                                     title: "\(job.title), \(job.company)")
                        }
                    } label: {
                        Label("Ask Espresso", systemImage: "sparkles")
                    }
                    .buttonStyle(.bordered)
                    .help("Work on this job with Espresso: outreach, answers, cover letter")
                }
            }
            .font(.system(size: 11))
            .padding(.top, 2)
        }
    }

    /// The first message, into Gmail drafts: Draft email, then a way to it
    /// while it waits there, then that it was sent.
    @ViewBuilder
    private func emailButton(_ lead: JobLeadDetail) -> some View {
        let job = lead.summary
        if !(lead.approach?.outreach?.body ?? "").isEmpty {
            if job.emailDraftId != nil, job.emailSentAt == nil {
                // Only the draft already in Gmail: if it was sent or deleted
                // there, the pane says so and nothing is made. Draft email is
                // what makes a new one.
                Button {
                    Task {
                        if let id = await vm.draftEmail(leadId: job.id, existingOnly: true) {
                            appState.openEmailDrafts(draftId: id)
                        }
                    }
                } label: {
                    Label("Edit draft in Email", systemImage: "envelope.open")
                }
                .buttonStyle(.bordered)
                .disabled(vm.busy)
                .help("It's in your Gmail drafts: edit it and send it from Email")
            } else if job.emailSentAt != nil {
                Label("Email sent", systemImage: "checkmark.circle")
                    .foregroundColor(appState.themeTextSecondary)
            } else {
                Button {
                    Task {
                        if let id = await vm.draftEmail(leadId: job.id) { appState.openEmailDrafts(draftId: id) }
                    }
                } label: {
                    Label("Draft email", systemImage: "envelope")
                }
                .buttonStyle(.bordered)
                .disabled(vm.busy)
                .help("Puts the first message in your Gmail drafts, to edit and send from Email. Nothing is sent.")
            }
        }
    }

    // MARK: Pay

    private func paySection(_ lead: JobLeadDetail) -> some View {
        section("Pay") {
            if lead.comp.parts.isEmpty {
                Text("This posting doesn't state pay.")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
            }
            ForEach(Array(lead.comp.parts.enumerated()), id: \.offset) { _, pair in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(pair.0).font(.system(size: 11, weight: .semibold)).frame(width: 52, alignment: .leading)
                        Text(JobSearchViewModel.partLine(pair.0, pair.1))
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText)
                    }
                    if let evidence = pair.1.evidence, let quote = evidence.quote, !quote.isEmpty {
                        HStack(alignment: .top, spacing: 4) {
                            Text("\u{201C}\(quote)\u{201D}")
                                .font(.system(size: 11).italic())
                                .foregroundColor(appState.themeTextSecondary)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                            if let url = JobSearchViewModel.webURL(evidence.url) {
                                Button { NSWorkspace.shared.open(url) } label: {
                                    Image(systemName: "link").font(.system(size: 10))
                                }
                                .buttonStyle(.plain)
                                .help(evidence.originLabel)
                            }
                        }
                        .padding(.leading, 56)
                    }
                }
            }
            if let hint = lead.payLawHint, !hint.isEmpty {
                Label(hint, systemImage: "scale.3d")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    // MARK: Approach

    @ViewBuilder
    private func approachSection(_ lead: JobLeadDetail) -> some View {
        let job = lead.summary
        section("How to approach it", trailing: {
            if !job.isDrafting && (vm.selectedSearch?.canDraft ?? false) {
                Button(lead.approach == nil ? "Draft" : "Redraft") { Task { await vm.redraft() } }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeAccent)
                    .disabled(vm.busy)
            }
        }) {
            if job.isDrafting {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text("Researching the company and drafting…")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                }
            } else if let approach = lead.approach {
                approachBody(approach)
            } else {
                Text(job.approachStatus == "failed"
                     ? "Drafting didn't finish for this job. Try Redraft."
                     : "Approaches are drafted for the top-ranked jobs. Draft one for this job any time.")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    @ViewBuilder
    private func approachBody(_ approach: JobApproach) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(approach.channelLabel)
                .font(.system(size: 10, weight: .semibold))
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Capsule().fill(appState.themeAccent.opacity(0.12)))
            if let summary = approach.summary {
                Text(summary)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
        }
        bullets("Steps", approach.steps, numbered: true)
        bullets("What to lead with", approach.talkingPoints)
        bullets("On pay", approach.negotiation)
        if !approach.contacts.isEmpty {
            subheading("People")
            ForEach(approach.contacts, id: \.self) { contact in
                HStack(spacing: 6) {
                    Text(contact.name).font(.system(size: 12, weight: .semibold))
                    if let role = contact.role, !role.isEmpty {
                        Text(role).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                    }
                    if let url = JobSearchViewModel.webURL(contact.sourceUrl) {
                        Button { NSWorkspace.shared.open(url) } label: { Image(systemName: "link").font(.system(size: 10)) }
                            .buttonStyle(.plain)
                            .help("Where they're named")
                    }
                }
            }
        }
        if let outreach = approach.outreach, !(outreach.body ?? "").isEmpty {
            draftBox(
                "First message",
                header: [outreach.toEmail.map { "To: \($0)" }, outreach.subject.map { "Subject: \($0)" }]
                    .compactMap { $0 }.joined(separator: "\n"),
                text: outreach.body ?? "",
                copyText: [outreach.subject.map { "Subject: \($0)\n\n" } ?? "", outreach.body ?? ""].joined(),
                extra: nil
            )
            let placeholders = EmailDraftsViewModel.placeholders(in: (outreach.subject ?? "") + "\n" + (outreach.body ?? ""))
            if !placeholders.isEmpty {
                Text("Fill in \(placeholders.joined(separator: ", ")) before you send it. Draft email puts it in Gmail, where you can.")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        if !approach.answers.isEmpty {
            subheading("Application answers")
            ForEach(Array(approach.answers.enumerated()), id: \.offset) { _, answer in
                draftBox(answer.question + (answer.likely == true ? "  (likely question)" : ""),
                         header: "", text: answer.answer, copyText: answer.answer, extra: nil)
            }
        }
        if !approach.unanswered.isEmpty {
            subheading("Answer these yourself")
            ForEach(Array(approach.unanswered.enumerated()), id: \.offset) { _, question in
                Text("\u{2022} \(question.text)")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
        if let letter = approach.coverLetter, !letter.isEmpty {
            draftBox("Cover letter", header: "", text: letter, copyText: letter, extra: nil)
        }
        if !approach.sources.isEmpty {
            subheading("Sources")
            ForEach(approach.sources, id: \.self) { source in
                if let url = JobSearchViewModel.webURL(source) {
                    Button { NSWorkspace.shared.open(url) } label: {
                        Label(url.host() ?? source, systemImage: "link").font(.system(size: 11)).lineLimit(1)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(appState.themeTextSecondary)
                }
            }
        }
    }

    // MARK: Notes + description

    private func notesSection(_ lead: JobLeadDetail) -> some View {
        section("Your notes", trailing: {
            if notes != lead.notes {
                Button("Save") { Task { await vm.saveNotes(notes, leadId: lead.summary.id) } }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeAccent)
                    .disabled(vm.busy)
            }
        }) {
            TextEditor(text: $notes)
                .font(.system(size: 12))
                .frame(minHeight: 60)
                .scrollContentBackground(.hidden)
                .padding(6)
                .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeText.opacity(0.04)))
        }
    }

    private func descriptionSection(_ text: String) -> some View {
        section("The posting") {
            Text(JobSearchViewModel.tidyPosting(text))
                .font(.system(size: 11))
                .foregroundColor(appState.themeText)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Building blocks

    private func section<Content: View, Trailing: View>(
        _ title: String,
        @ViewBuilder trailing: () -> Trailing = { EmptyView() },
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                trailing()
            }
            content()
        }
    }

    private func subheading(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(appState.themeText)
            .padding(.top, 4)
    }

    @ViewBuilder
    private func bullets(_ title: String, _ items: [String], numbered: Bool = false) -> some View {
        if !items.isEmpty {
            subheading(title)
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(alignment: .top, spacing: 6) {
                    Text(numbered ? "\(index + 1)." : "\u{2022}")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .frame(width: 14, alignment: .trailing)
                    Text(item)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func draftBox(_ title: String, header: String, text: String, copyText: String,
                          extra: AnyView?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                if let extra { extra.font(.system(size: 11)) }
                Button(copied == copyText ? "Copied" : "Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(copyText, forType: .string)
                    copied = copyText
                }
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(appState.themeAccent)
            }
            if !header.isEmpty {
                Text(header)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .textSelection(.enabled)
            }
            Text(text)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(appState.themeText.opacity(0.04)))
    }
}
