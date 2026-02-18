import { Link } from 'react-router-dom';

const sections = [
  {
    title: '1. Scope and Acceptance',
    body: [
      'These Terms of Service ("Terms") govern access to and use of the Matcha platform, websites, voice interview tools, policy and handbook tools, HR workflow tools, AI copilots, APIs, and related services (collectively, the "Services").',
      'By using the Services, you agree to these Terms on behalf of yourself and, if applicable, the company or organization you represent. If you do not agree, do not use the Services.',
    ],
  },
  {
    title: '2. Eligibility and Accounts',
    body: [
      'You must be legally able to enter contracts and use the Services only for lawful business purposes.',
      'You are responsible for account credentials, user permissions, and all activity under your account. You must promptly notify Matcha of unauthorized access.',
    ],
  },
  {
    title: '3. Matcha Service Modules',
    body: [
      'The Services may include workforce onboarding, policy distribution and acknowledgment, compliance support, incident reporting, employee data management, candidate workflows, offer letter workflows, voice screening, and AI-assisted analysis and recommendations.',
      'Some modules are optional, in beta, or subject to feature flags. Availability may vary by plan, region, and technical constraints.',
    ],
  },
  {
    title: '4. Customer Data and Inputs',
    body: [
      'You retain ownership of data, documents, audio, text, and materials you upload or submit ("Customer Data").',
      'You grant Matcha the rights needed to host, process, transmit, analyze, and display Customer Data solely to provide, secure, improve, and support the Services in accordance with applicable law and your configuration choices.',
    ],
  },
  {
    title: '5. AI and Voice Features',
    body: [
      'AI and voice outputs may contain errors and should be reviewed by qualified personnel before use in legal, HR, hiring, safety, payroll, or disciplinary decisions.',
      'Matcha does not provide legal advice. You remain responsible for final policy decisions, employment actions, and legal compliance outcomes.',
    ],
  },
  {
    title: '6. Compliance and Jurisdictional Content',
    body: [
      'Matcha may provide regulatory references, confidence signals, and jurisdictional guidance. This content is informational and may not reflect the most current legal developments at all times.',
      'You are responsible for validating requirements that apply to your organization and locations, including city, county, state, and federal obligations.',
    ],
  },
  {
    title: '7. Acceptable Use',
    body: [
      'You may not use the Services to violate law, discriminate unlawfully, infringe intellectual property rights, transmit malware, interfere with systems, scrape without authorization, or reverse engineer protected functionality except where law permits.',
      'You may not use the Services to generate deceptive content, impersonation, or unlawful surveillance.',
    ],
  },
  {
    title: '8. Security and Privacy',
    body: [
      'Matcha implements administrative, technical, and organizational safeguards intended to protect Service data.',
      'Use of personal data is governed by Matcha privacy disclosures and applicable data processing terms. You are responsible for obtaining any required notices and consents from your workforce, candidates, and users.',
    ],
  },
  {
    title: '9. Integrations and Third-Party Services',
    body: [
      'The Services may connect with third-party providers (for example communication, storage, identity, and productivity platforms). Those providers are governed by their own terms and privacy practices.',
      'Matcha is not responsible for third-party outages, policy changes, or acts and omissions outside Matcha control.',
    ],
  },
  {
    title: '10. Fees, Billing, and Plan Changes',
    body: [
      'Paid features require payment of applicable fees under your order form, subscription, or other commercial terms.',
      'Unless otherwise agreed in writing, fees are non-refundable, taxes are your responsibility, and Matcha may suspend paid Services for overdue amounts after notice.',
    ],
  },
  {
    title: '11. Intellectual Property',
    body: [
      'Matcha and its licensors own all rights in the Services, software, models, interfaces, branding, and documentation, except Customer Data and third-party materials.',
      'No rights are granted except as expressly stated in these Terms.',
    ],
  },
  {
    title: '12. Confidentiality',
    body: [
      'Each party may receive confidential information from the other and will protect it using reasonable care, using it only for permitted purposes under these Terms.',
      'Confidentiality obligations survive termination for as long as information remains confidential.',
    ],
  },
  {
    title: '13. Disclaimer of Warranties',
    body: [
      'To the maximum extent permitted by law, the Services are provided "as is" and "as available" without warranties of any kind, express or implied, including merchantability, fitness for a particular purpose, and non-infringement.',
      'Matcha does not warrant uninterrupted operation, error-free outputs, or legal sufficiency of generated content.',
    ],
  },
  {
    title: '14. Limitation of Liability',
    body: [
      'To the maximum extent permitted by law, Matcha is not liable for indirect, incidental, special, consequential, exemplary, or punitive damages, or for loss of profits, revenue, goodwill, or data.',
      'Matcha aggregate liability arising out of or related to the Services will not exceed the amounts paid or payable by you for the Services in the 12 months before the claim, unless a different limit is required by law or a signed agreement.',
    ],
  },
  {
    title: '15. Termination',
    body: [
      'You may stop using the Services at any time. Matcha may suspend or terminate access for material breach, security risk, legal requirements, or non-payment, subject to applicable notice obligations.',
      'Sections that by nature should survive termination will survive, including payment obligations, confidentiality, ownership, warranty disclaimers, liability limits, and dispute terms.',
    ],
  },
  {
    title: '16. Changes, Governing Law, and Contact',
    body: [
      'Matcha may update these Terms from time to time. Material updates will be posted with a revised effective date. Continued use after the effective date constitutes acceptance of revised Terms.',
      'These Terms are governed by applicable law as defined in your commercial agreement or, if none applies, the laws of the jurisdiction where Matcha is organized, excluding conflict-of-law rules.',
      'Questions about these Terms: legal@hey-matcha.com.',
    ],
  },
];

export default function TermsOfService() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-5xl mx-auto px-6 py-12 md:py-16">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-10">
          <Link
            to="/"
            className="text-xs font-mono uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
          >
            Back to Landing
          </Link>
          <span className="text-xs font-mono uppercase tracking-widest text-zinc-500">
            Effective Date: February 18, 2026
          </span>
        </div>

        <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-4">Terms of Service</h1>
        <p className="text-zinc-400 text-sm md:text-base leading-relaxed max-w-3xl mb-12">
          These Terms are designed to cover all core aspects of the Matcha app and related Services,
          including onboarding, compliance tooling, policy workflows, voice interview agents, AI assistance,
          integrations, billing, and platform usage standards.
        </p>

        <div className="space-y-10">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="text-xl md:text-2xl font-semibold tracking-tight mb-3">{section.title}</h2>
              <div className="space-y-3">
                {section.body.map((paragraph) => (
                  <p key={paragraph} className="text-zinc-300 leading-relaxed">
                    {paragraph}
                  </p>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
