import { Link } from 'react-router-dom';

const sections = [
  {
    title: '1. Referral Commission',
    body: [
      'As a Broker Partner, you are entitled to a ten percent (10%) recurring commission on the base subscription fees paid by any team or company you refer to Matcha, for as long as they remain an active paying customer and you remain an active Broker Partner.',
      'Commissions are calculated on net revenue (excluding taxes and third-party fees) and are paid out according to our standard partner payment schedule.',
    ],
  },
  {
    title: '2. Liability and Service Warranty',
    body: [
      'Matcha provide its services "as is" and "as available". While we strive for high reliability and accuracy, Matcha shall not be liable for any issues, errors, or service interruptions that may occur.',
      'Broker Partner agrees that Matcha is not responsible for any advice, guidance, or compliance outcomes provided through the platform to referred clients. The final responsibility for HR and legal compliance remains with the client.',
    ],
  },
  {
    title: '3. Relationship of Parties',
    body: [
      'The relationship between Matcha and Broker Partner is that of independent contractors. Nothing in these terms creates a partnership, joint venture, or agency relationship.',
      'Broker Partners have no authority to bind Matcha to any contract or obligation.',
    ],
  },
  {
    title: '4. Termination',
    body: [
      'Either party may terminate the partner relationship at any time upon written notice. Upon termination, the right to receive new commissions may cease depending on the specific reason for termination.',
    ],
  },
];

export default function BrokerPartnerTerms() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 md:p-12">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <Link
            to="/app/broker/reporting"
            className="text-xs font-mono uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
          >
            ← Back to Reporting
          </Link>
          <span className="text-xs font-mono uppercase tracking-widest text-zinc-500">
            Effective Date: February 24, 2026
          </span>
        </div>

        <h1 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">Broker Partner Terms</h1>
        <p className="text-zinc-400 text-sm md:text-base leading-relaxed max-w-3xl mb-12">
          These terms govern our partnership with brokers who refer clients to the Matcha platform. 
          By participating in the partner program and accessing reporting, you agree to these terms.
        </p>

        <div className="space-y-10">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="text-xl md:text-2xl font-semibold tracking-tight mb-3 text-amber-500">{section.title}</h2>
              <div className="space-y-3">
                {section.body.map((paragraph, idx) => (
                  <p key={idx} className="text-zinc-300 leading-relaxed">
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
