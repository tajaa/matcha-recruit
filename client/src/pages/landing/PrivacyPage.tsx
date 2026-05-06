import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'

const INK = '#1F1D1A'
const BG = '#F5F2ED'
const MUTED = '#6B6760'
const LINE = '#E4DED2'
const DISPLAY = 'var(--font-display)'

const LAST_UPDATED = 'May 1, 2025'

export default function PrivacyPage() {
  return (
    <div style={{ backgroundColor: BG, color: INK, colorScheme: 'light' }} className="min-h-screen">
      <MarketingNav />
      <main className="max-w-[800px] mx-auto px-6 sm:px-10 pt-32 pb-24">
        <p className="text-[10px] font-mono uppercase tracking-[0.4em] mb-4" style={{ color: '#b48228' }}>
          Legal // Privacy
        </p>
        <h1 className="text-4xl font-bold tracking-tight mb-3" style={{ fontFamily: DISPLAY, fontWeight: 500 }}>
          Privacy Policy
        </h1>
        <p className="text-sm mb-12" style={{ color: MUTED }}>Last updated {LAST_UPDATED}</p>

        <div className="space-y-10 text-sm leading-relaxed">
          <Section title="1. Information We Collect">
            <p>We collect information you provide directly (account registration, form submissions, service requests), information generated through your use of the Services (usage logs, feature interactions, AI query content), and limited technical data (IP address, browser type, device identifiers) for security and performance purposes.</p>
          </Section>

          <Section title="2. How We Use Your Information">
            <p>We use collected information to:</p>
            <ul className="list-disc pl-5 space-y-1 mt-2" style={{ color: MUTED }}>
              <li>Deliver, maintain, and improve the Services</li>
              <li>Process transactions and send related notices</li>
              <li>Respond to support requests and inquiries</li>
              <li>Send product updates and compliance-relevant communications (you may opt out)</li>
              <li>Detect and prevent fraud, abuse, or security incidents</li>
              <li>Fulfill legal obligations and enforce our Terms of Service</li>
            </ul>
          </Section>

          <Section title="3. Sharing of Information">
            <p>We do not sell your personal information. We share data only with:</p>
            <ul className="list-disc pl-5 space-y-1 mt-2" style={{ color: MUTED }}>
              <li><strong style={{ color: INK }}>Service providers</strong> who process data on our behalf (hosting, payments, email delivery) under data processing agreements</li>
              <li><strong style={{ color: INK }}>Your organization's administrators</strong> who have contracted access to company-level data</li>
              <li><strong style={{ color: INK }}>Legal authorities</strong> when required by law, court order, or to protect rights and safety</li>
              <li><strong style={{ color: INK }}>Successor entities</strong> in connection with a merger, acquisition, or asset sale, with notice to affected users</li>
            </ul>
          </Section>

          <Section title="4. Data Retention">
            <p>We retain your data for as long as your account is active or as needed to deliver the Services. Following account termination, we retain data for up to ninety (90) days to allow for account recovery, then delete or anonymize it unless a longer retention period is required by law.</p>
          </Section>

          <Section title="5. Security">
            <p>We implement administrative, technical, and physical safeguards designed to protect your information. Data in transit is encrypted via TLS. Access to production systems is restricted to authorized personnel. We conduct regular security reviews and promptly address identified vulnerabilities.</p>
          </Section>

          <Section title="6. Cookies and Tracking">
            <p>We use cookies and similar technologies to maintain sessions, remember preferences, and analyze aggregate usage patterns. We do not use third-party advertising cookies. You may disable cookies in your browser settings, though some features may not function as intended.</p>
          </Section>

          <Section title="7. Your Rights">
            <p>Depending on your jurisdiction, you may have the right to access, correct, or delete your personal data; to object to certain processing; and to data portability. To exercise these rights, contact us at <a href="mailto:privacy@matchahq.com" className="underline underline-offset-2" style={{ color: INK }}>privacy@matchahq.com</a>. We respond to all requests within thirty (30) days.</p>
          </Section>

          <Section title="8. California Residents (CCPA)">
            <p>California residents have additional rights under the California Consumer Privacy Act, including the right to know what personal information we collect, the right to delete, and the right to opt out of sale (we do not sell personal information). To submit a CCPA request, contact <a href="mailto:privacy@matchahq.com" className="underline underline-offset-2" style={{ color: INK }}>privacy@matchahq.com</a>.</p>
          </Section>

          <Section title="9. International Transfers">
            <p>Our Services are operated from the United States. If you are located outside the U.S., your information may be transferred to and processed in the U.S. We use standard contractual clauses and other appropriate safeguards for cross-border transfers.</p>
          </Section>

          <Section title="10. Children's Privacy">
            <p>The Services are not directed to individuals under the age of 18. We do not knowingly collect personal information from minors. If we become aware of such collection, we will promptly delete the data.</p>
          </Section>

          <Section title="11. Changes to This Policy">
            <p>We may update this Privacy Policy to reflect changes in our practices or applicable law. We will post the updated policy with a revised "last updated" date and notify you of material changes via email or in-platform notice.</p>
          </Section>

          <Section title="12. Contact">
            <p>Questions or concerns about this Privacy Policy? Contact our privacy team at <a href="mailto:privacy@matchahq.com" className="underline underline-offset-2" style={{ color: INK }}>privacy@matchahq.com</a> or write to Matcha, Inc., Attn: Privacy, [Address].</p>
          </Section>
        </div>
      </main>
      <MarketingFooter />
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="pb-4 mb-5"
        style={{ borderBottom: `1px solid ${LINE}` }}
      >
        <h2 className="text-base font-semibold tracking-tight" style={{ color: INK }}>{title}</h2>
      </div>
      <div style={{ color: MUTED }}>{children}</div>
    </div>
  )
}
