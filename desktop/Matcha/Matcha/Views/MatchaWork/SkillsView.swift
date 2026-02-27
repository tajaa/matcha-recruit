import SwiftUI

struct SkillsView: View {
    var body: some View {
        ZStack {
            Color.appBackground.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 32) {
                    // Header
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 10) {
                            Image(systemName: "bolt.fill")
                                .font(.system(size: 20))
                                .foregroundColor(.matcha500)
                            Text("Skills")
                                .font(.system(size: 22, weight: .bold))
                                .foregroundColor(.white)
                        }
                        Text("Everything is natural language — just describe what you need in a chat. Each skill is detected automatically from your message.")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    // Skills
                    SkillCard(
                        icon: "doc.text.fill",
                        name: "Offer Letters",
                        color: .matcha500,
                        description: "Draft, refine, and send offer letters to candidates. The AI fills in salary, title, start date, and other details based on your instructions, and can email the draft directly to the candidate.",
                        triggers: [
                            "Write an offer letter for Jane as a Senior Engineer",
                            "Create a job offer for the product manager role at $120k",
                            "Draft an employment offer starting March 1st"
                        ],
                        operations: [
                            SkillOperation(name: "Refine", description: "Change any field — salary, title, start date, clauses — just ask"),
                            SkillOperation(name: "Save draft", description: "\"Save the draft\" — stores it in Offer Letters for later"),
                            SkillOperation(name: "Send draft", description: "\"Send the draft to jane@example.com\" — emails the candidate"),
                            SkillOperation(name: "Finalize", description: "Use the Finalize button — locks the thread and removes watermarks"),
                        ]
                    )

                    SkillCard(
                        icon: "star.fill",
                        name: "Performance Reviews",
                        color: .yellow,
                        description: "Create structured, anonymized performance reviews. Collects feedback from multiple reviewers, synthesizes it, and can send review requests by email.",
                        triggers: [
                            "Create a performance review for the engineering team",
                            "Start an anonymized review cycle for Q1",
                            "Write a quarterly evaluation for our designers"
                        ],
                        operations: [
                            SkillOperation(name: "Build review", description: "Describe the role, team, or individual — AI drafts the structure"),
                            SkillOperation(name: "Send requests", description: "\"Send review requests to the team\" — emails reviewers"),
                            SkillOperation(name: "Finalize", description: "Use the Finalize button — locks and publishes the review"),
                        ]
                    )

                    SkillCard(
                        icon: "book.fill",
                        name: "Workbooks",
                        color: .blue,
                        description: "Build onboarding workbooks, training manuals, handbooks, and playbooks. Can generate a presentation and send it to employees for signature.",
                        triggers: [
                            "Create an onboarding workbook for new engineers",
                            "Build a sales playbook with our process",
                            "Write a policy handbook covering PTO and remote work"
                        ],
                        operations: [
                            SkillOperation(name: "Build sections", description: "Describe the content — AI drafts sections and structure"),
                            SkillOperation(name: "Generate presentation", description: "\"Generate a presentation\" — creates slides from the workbook"),
                            SkillOperation(name: "Send for signature", description: "\"Send to employees for signature\" — sends to your team"),
                        ]
                    )

                    SkillCard(
                        icon: "person.badge.plus.fill",
                        name: "Onboarding",
                        color: .purple,
                        description: "Add new employees and manage their onboarding flows. Describe the new hires and the AI creates the employee records.",
                        triggers: [
                            "Onboard three new engineers starting Monday",
                            "Add Jane Smith as a Product Manager in London",
                            "Create employees for the new sales hires"
                        ],
                        operations: [
                            SkillOperation(name: "Create employees", description: "\"Create the employees\" — adds the records once details are confirmed"),
                        ]
                    )

                    // Tips
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Tips")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.secondary)

                        TipRow(text: "Each chat thread stays focused on one skill. Start a new chat to switch skills.")
                        TipRow(text: "You can change any field just by asking — \"make the salary $140k\" or \"change the start date\".")
                        TipRow(text: "Use the version history button (clock icon) to revert to any earlier draft.")
                        TipRow(text: "Finalized threads are locked but the documents remain in Matcha Elements.")
                    }
                    .padding(16)
                    .background(Color.zinc800.opacity(0.5))
                    .cornerRadius(10)
                }
                .padding(32)
                .frame(maxWidth: 680, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

private struct SkillOperation {
    let name: String
    let description: String
}

private struct SkillCard: View {
    let icon: String
    let name: String
    let color: Color
    let description: String
    let triggers: [String]
    let operations: [SkillOperation]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Title row
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 15))
                    .foregroundColor(color)
                    .frame(width: 28, height: 28)
                    .background(color.opacity(0.12))
                    .cornerRadius(6)
                Text(name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
            }

            Text(description)
                .font(.system(size: 13))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            // Trigger phrases
            VStack(alignment: .leading, spacing: 4) {
                Text("Example phrases")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                    .textCase(.uppercase)
                    .tracking(0.5)

                VStack(alignment: .leading, spacing: 4) {
                    ForEach(triggers, id: \.self) { phrase in
                        HStack(spacing: 6) {
                            Text("\"")
                                .foregroundColor(.secondary)
                                + Text(phrase)
                                .foregroundColor(.white)
                                + Text("\"")
                                .foregroundColor(.secondary)
                        }
                        .font(.system(size: 12, design: .monospaced))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.zinc950)
                        .cornerRadius(6)
                    }
                }
            }

            // Operations
            if !operations.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("What it can do")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                        .textCase(.uppercase)
                        .tracking(0.5)

                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(operations, id: \.name) { op in
                            HStack(alignment: .top, spacing: 8) {
                                Text(op.name)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(color)
                                    .frame(width: 130, alignment: .leading)
                                Text(op.description)
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color.zinc800.opacity(0.4))
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.borderColor.opacity(0.5), lineWidth: 1)
        )
    }
}

private struct TipRow: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text("·")
                .foregroundColor(.secondary)
            Text(text)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
