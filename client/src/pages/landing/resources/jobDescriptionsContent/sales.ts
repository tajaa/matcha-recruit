import type { JDContent } from './types'

export const sales: Record<string, JDContent> = {
  'account-executive': {
    summary: 'The Account Executive owns the full sales cycle for a defined territory or segment — from pipeline generation and discovery through negotiation and close. You will carry a quota, build multi-threaded champion relationships, and partner with Sales Engineering, Marketing, and Customer Success to win and expand strategic accounts.',
    responsibilities: [
      'Develop and execute a territory plan to build a pipeline at or above quota coverage targets',
      'Run a structured sales process: discovery, demo, business-case development, negotiation, close',
      'Qualify opportunities rigorously using MEDDIC, SPICED, or equivalent framework',
      'Build multi-threaded relationships across economic buyers, champions, and technical evaluators',
      'Forecast accurately in CRM (Salesforce, HubSpot) and maintain rigorous pipeline hygiene',
      'Partner with Solutions Engineering on POCs and technical evaluation processes',
      'Collaborate with Customer Success on expansion and renewal strategy for key accounts',
    ],
    requirements: [
      '3+ years of full-cycle B2B SaaS or enterprise software sales experience',
      'Demonstrated track record of meeting or exceeding quota',
      'Proficiency with sales CRM (Salesforce or HubSpot) and outbound tooling (Outreach, Apollo)',
      'Strong business-case development and ROI storytelling skills',
      'Excellent discovery, negotiation, and executive communication skills',
    ],
    preferred: [
      'Experience selling to HR, Finance, or Operations buyers',
      'MEDDIC/MEDDICC or SPICED sales methodology certification or training',
      'Startup AE experience including self-serve pipeline generation',
    ],
  },

  'sdr': {
    summary: 'The Sales Development Representative (SDR) generates qualified pipeline for the Account Executive team through outbound prospecting and inbound lead qualification. You will research target accounts, execute multi-touch sequences, and connect prospects to the right AE — building the discipline and craft to advance into a closing role.',
    responsibilities: [
      'Research target accounts and build prospect lists using ZoomInfo, LinkedIn Sales Navigator, or equivalent',
      'Execute outbound prospecting sequences via email, phone, and LinkedIn',
      'Qualify inbound marketing leads and convert them to sales-accepted opportunities',
      'Conduct discovery calls to identify pain, urgency, and budget fit',
      'Hand off qualified opportunities to Account Executives with full context and documentation',
      'Maintain accurate activity and pipeline records in the CRM',
      'Collaborate with Marketing on messaging iteration and campaign feedback',
    ],
    requirements: [
      '1+ year of SDR, BDR, or inside sales experience (internships or recent graduates considered)',
      'Strong written communication and cold-outreach skills',
      'Proficiency with sales engagement platforms (Outreach, Salesloft, Apollo, or equivalent)',
      'High activity level, coachability, and resilience',
      'Goal-oriented with a track record of hitting daily/weekly KPIs',
    ],
    preferred: [
      'Experience prospecting into HR, Operations, or Finance buyers',
      'Salesforce or HubSpot CRM proficiency',
      "Bachelor's degree in Business, Communications, or related field",
    ],
  },

  'customer-success-manager': {
    summary: 'The Customer Success Manager owns the post-sale relationship for a portfolio of accounts, driving adoption, retention, and expansion. You will partner with customers to ensure they achieve their desired outcomes, conduct regular business reviews, and identify growth opportunities — serving as the voice of the customer internally.',
    responsibilities: [
      'Own the success of a book of business including onboarding, adoption, renewal, and expansion',
      'Conduct regular Executive Business Reviews (EBRs) and health-check calls',
      'Build and maintain relationships with stakeholders at multiple levels within customer accounts',
      'Monitor product usage data and proactively engage at-risk customers',
      'Identify, qualify, and facilitate expansion and upsell opportunities with the AE team',
      'Serve as the escalation point for customer issues and drive resolution cross-functionally',
      'Capture product feedback and represent the customer perspective to Product and Engineering',
    ],
    requirements: [
      '3+ years of customer success, account management, or client services experience in SaaS',
      'Demonstrated retention and expansion track record',
      'Strong executive-communication and relationship-building skills',
      'Proficiency with CS platforms (Gainsight, ChurnZero, or Totango) and CRM',
      'Analytical ability to use product data and health metrics to drive outcomes',
    ],
    preferred: [
      'Experience managing enterprise accounts ($100K+ ARR)',
      'Domain expertise in HR Tech, Fintech, or vertical SaaS',
      'Salesforce or HubSpot CRM advanced proficiency',
    ],
  },

  'marketing-manager': {
    summary: 'The Marketing Manager plans and executes integrated marketing programs across demand generation, content, and brand. You will manage channels, own the content calendar, partner with Sales to support pipeline goals, and ensure consistent, high-quality brand expression across all customer touchpoints.',
    responsibilities: [
      'Develop and execute integrated marketing campaigns across email, paid, social, and organic channels',
      'Own and manage the content calendar; coordinate content production with internal and external contributors',
      'Track, analyze, and report on campaign performance, optimizing for pipeline and MQL targets',
      'Partner with Sales to align on ICP, messaging, and campaign-to-close feedback',
      'Manage relationships with agencies, freelancers, and marketing technology vendors',
      'Maintain brand standards across all marketing materials and digital properties',
      'Manage the marketing budget and ensure programs deliver measurable ROI',
    ],
    requirements: [
      '4+ years of B2B or B2C marketing experience',
      'Proven success running multi-channel demand-generation campaigns',
      'Proficiency with marketing automation (HubSpot, Marketo, or Pardot) and CRM',
      'Strong analytical skills and experience with marketing attribution',
      'Excellent written communication and brand sensibility',
    ],
    preferred: [
      'Experience marketing to SMB or mid-market audiences',
      'Hands-on paid media management (Google Ads, LinkedIn Ads)',
      'Google Analytics 4 certification or equivalent',
    ],
  },

  'content-marketer': {
    summary: 'The Content Marketer creates and distributes content that attracts, educates, and converts the target audience. You will own blog, email, SEO, and social content — developing a consistent editorial voice while building organic traffic and nurturing prospects through the funnel.',
    responsibilities: [
      'Research and write long-form blog posts, guides, and thought leadership content optimized for SEO',
      'Develop email nurture sequences, newsletters, and campaign copy',
      'Plan and execute social media content across LinkedIn, Twitter/X, and other relevant channels',
      'Conduct keyword research and maintain an SEO content roadmap aligned with organic traffic goals',
      'Repurpose content across formats (blog → social → email → video scripts)',
      'Track content performance through Google Search Console, GA4, and HubSpot',
      'Collaborate with designers, subject-matter experts, and external contributors',
    ],
    requirements: [
      '3+ years of content marketing experience with a strong writing portfolio',
      'Demonstrated SEO knowledge including keyword research, on-page optimization, and link building',
      'Experience with email marketing platforms (HubSpot, Mailchimp, Klaviyo, or similar)',
      'Strong editorial judgment and ability to adapt tone for different audiences',
      'Data-driven mindset with experience measuring content performance',
    ],
    preferred: [
      'HubSpot Content Marketing or Google Analytics certification',
      'Experience with video scripts, podcasts, or webinar content',
      'Technical writing or domain expertise in HR, Legal, Finance, or SaaS',
    ],
  },

  'social-media-manager': {
    summary: "The Social Media Manager owns the company's presence across social platforms — developing strategy, creating content, managing the community, and measuring impact. You will build brand affinity, drive engagement, and support broader marketing and business development goals through authentic, platform-native content.",
    responsibilities: [
      'Develop and execute platform-specific social media strategies for LinkedIn, Instagram, X/Twitter, TikTok, and others',
      'Create, schedule, and publish organic content aligned with the editorial calendar',
      'Monitor, respond to, and engage with community comments, mentions, and DMs',
      'Manage paid social campaigns in coordination with the Demand Generation team',
      'Track and report on follower growth, reach, engagement, and conversion from social channels',
      'Stay current on platform algorithm changes, trends, and format innovations',
      'Collaborate with design, content, and PR teams to produce high-quality assets',
    ],
    requirements: [
      '3+ years of social media management experience for a brand or agency',
      'Demonstrated ability to grow followers and engagement across multiple platforms',
      'Proficiency with social media management tools (Sprout Social, Buffer, Hootsuite, or similar)',
      'Basic graphic design skills (Canva, Adobe Express) for post creation',
      'Strong copywriting skills and native platform sensibility',
    ],
    preferred: [
      'Experience with paid social advertising (Meta Ads, LinkedIn Campaign Manager)',
      'Video production and short-form video editing skills (CapCut, Premiere Rush)',
      'Influencer or creator partnership experience',
    ],
  },
}
