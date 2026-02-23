import type {
  CompanyHandbookProfile,
  HandbookMode,
  HandbookSourceType,
} from '../../types';

export type WizardCardKind =
  | 'title'
  | 'mode'
  | 'source'
  | 'industry'
  | 'sub_industry'
  | 'states'
  | 'legal_name'
  | 'dba'
  | 'ceo'
  | 'headcount'
  | 'profile_bool'
  | 'policy_pack'
  | 'guided_followup'
  | 'custom_sections'
  | 'upload'
  | 'review';

export interface WizardHelperCopy {
  meaning: string;
  goodAnswer: string;
  avoid: string;
}

interface IndustryHelperPack {
  meaning: string;
  goodAnswer: string;
  avoid: string;
  stateOverlays?: Partial<Record<string, Partial<WizardHelperCopy>>>;
}

export interface WizardHelperContext {
  cardKind: WizardCardKind;
  mode: HandbookMode;
  sourceType: HandbookSourceType;
  industry: string;
  industryLabel: string;
  selectedStates: string[];
  profileKey?: keyof CompanyHandbookProfile;
  guidedQuestionPlaceholder?: string | null;
}

const PROFILE_BOOL_HELPER_COPY: Partial<Record<keyof CompanyHandbookProfile, WizardHelperCopy>> = {
  remote_workers: {
    meaning: 'Indicates whether any employee regularly works outside a company-controlled site.',
    goodAnswer: 'Select Yes if employees routinely work from home or other remote locations.',
    avoid: 'Do not select Yes for rare one-off remote days.',
  },
  minors: {
    meaning: 'Indicates whether your workforce includes employees under 18.',
    goodAnswer: 'Select Yes if minors are currently employed or expected to be hired.',
    avoid: 'Do not select No if seasonal hiring includes minors.',
  },
  tipped_employees: {
    meaning: 'Determines whether tip-credit and tip handling boilerplate is required.',
    goodAnswer: 'Select Yes if any role receives tips as compensation.',
    avoid: 'Do not select No when tip jars or digital tipping are active.',
  },
  tip_pooling: {
    meaning: 'Determines whether shared-tip policy language should be included.',
    goodAnswer: 'Select Yes only if tips are intentionally pooled or redistributed.',
    avoid: 'Do not select Yes if each worker keeps only their own tips.',
  },
  union_employees: {
    meaning: 'Signals whether union-specific labor language should be included.',
    goodAnswer: 'Select Yes if any covered bargaining unit exists.',
    avoid: 'Do not select No if a union contract is active for any location.',
  },
  federal_contracts: {
    meaning: 'Signals whether federal-contractor obligations may apply.',
    goodAnswer: 'Select Yes if the company performs work under federal contracts/subcontracts.',
    avoid: 'Do not guess; confirm with legal or operations if unsure.',
  },
  group_health_insurance: {
    meaning: 'Controls health-benefit references in handbook boilerplate.',
    goodAnswer: 'Select Yes only when a company-sponsored group health plan exists.',
    avoid: 'Do not select Yes for stipend-only or marketplace-only support.',
  },
  background_checks: {
    meaning: 'Controls pre-employment screening language and notices.',
    goodAnswer: 'Select Yes if background checks are part of your hiring workflow.',
    avoid: 'Do not select No if checks are performed for any role.',
  },
  hourly_employees: {
    meaning: 'Determines whether wage/hour and timekeeping language is emphasized.',
    goodAnswer: 'Select Yes if any non-exempt hourly employees exist.',
    avoid: 'Do not select No unless workforce is fully salaried/commissioned exempt.',
  },
  salaried_employees: {
    meaning: 'Determines whether salaried-exempt policy language is included.',
    goodAnswer: 'Select Yes if any employees are paid on a salary basis.',
    avoid: 'Do not assume all salaried roles are exempt; classification still matters.',
  },
  commissioned_employees: {
    meaning: 'Controls commission-plan and earnings disclosure references.',
    goodAnswer: 'Select Yes if any compensation includes commissions.',
    avoid: 'Do not select No when any sales role has variable commission pay.',
  },
};

const JURISDICTION_HELPER_NOTES: Partial<Record<string, string>> = {
  CA: 'CA generally requires stricter wage/hour, break, and reimbursement handling.',
  NY: 'NY/NYC policies often need tighter wage notice, harassment, and pay-transparency coordination.',
  IL: 'IL/Chicago operations often need clear paid-leave and scheduling alignment.',
  FL: 'FL/Miami operations should still confirm any city/county-specific overlays.',
};

// Add/adjust packs here to customize helper tone by industry without touching the wizard component.
export const INDUSTRY_HELPER_PACKS: Record<string, IndustryHelperPack> = {
  hospitality: {
    meaning: 'For hospitality, handbook logic prioritizes tipped-workforce and shift-operations controls.',
    goodAnswer: 'For cafes/restaurants, answer based on real shift flow, tip handling, and front-of-house/back-of-house staffing.',
    avoid: 'Avoid optimistic assumptions about breaks, tip handling, or scheduling that operations cannot consistently execute.',
  },
  technology: {
    meaning: 'For technology employers, handbook logic emphasizes remote/hybrid operations, data handling, and role classification.',
    goodAnswer: 'For tech teams, answer using real role mix (engineering, support, sales) and real remote-work patterns.',
    avoid: 'Avoid assuming all startup roles are exempt or that remote-work rules are informal.',
    stateOverlays: {
      CA: {
        goodAnswer: 'For a CA tech startup, classify exempt/non-exempt roles conservatively and document reimbursement expectations.',
        avoid: 'Avoid broad statements that every engineer is exempt without role-specific analysis.',
      },
    },
  },
  retail: {
    meaning: 'For retail employers, handbook logic emphasizes floor operations, timekeeping, and customer-facing escalation.',
    goodAnswer: 'Answer based on opening/closing routines, on-floor supervision, and sales-floor incident workflows.',
    avoid: 'Avoid policy language that conflicts with how stores actually staff and schedule.',
  },
  manufacturing: {
    meaning: 'For manufacturing/warehouse employers, handbook logic emphasizes safety-critical controls and shift handoffs.',
    goodAnswer: 'Answer with current plant/warehouse realities for safety ownership, training, and handoff protocol.',
    avoid: 'Avoid understating safety controls or incident escalation requirements.',
  },
  healthcare: {
    meaning: 'For healthcare employers, handbook logic emphasizes credentialing, patient-safety reporting, and accommodations.',
    goodAnswer: 'Answer using current clinical/non-clinical workflows and documented escalation paths.',
    avoid: 'Avoid generic language that bypasses credential, safety, or reporting obligations.',
  },
};

function defaultIndustryPack(industryLabel: string): IndustryHelperPack {
  return {
    meaning: `For ${industryLabel}, helper guidance focuses on baseline employer compliance behaviors.`,
    goodAnswer: `Answer with your current ${industryLabel.toLowerCase()} operating model, not future plans.`,
    avoid: 'Avoid placeholders that require major policy rewrites after launch.',
  };
}

function joinSentences(...parts: Array<string | undefined>): string {
  return parts.filter((part) => Boolean(part && part.trim())).join(' ');
}

function resolveBaseCopy(context: WizardHelperContext): WizardHelperCopy {
  const { cardKind, mode, profileKey, guidedQuestionPlaceholder } = context;

  if (cardKind === 'title') {
    return {
      meaning: 'This is the admin-visible name for your draft handbook.',
      goodAnswer: 'Use a specific title with year and scope, like "2026 CA + NY Employee Handbook".',
      avoid: 'Avoid generic names like "Final Handbook" or "Test".',
    };
  }

  if (cardKind === 'mode') {
    return {
      meaning: 'Defines whether this draft governs one state or multiple states.',
      goodAnswer: 'Use Single-State only for one jurisdiction; choose Multi-State for two or more states.',
      avoid: 'Avoid Single-State if you operate in multiple states.',
    };
  }

  if (cardKind === 'source') {
    return {
      meaning: 'Chooses whether Matcha generates boilerplate or you import an existing handbook.',
      goodAnswer: 'Use Template Builder for net-new drafts; use Upload when you already have a base handbook.',
      avoid: 'Avoid Upload unless the document is current and reviewable.',
    };
  }

  if (cardKind === 'industry') {
    return {
      meaning: 'Industry selects compliance and policy defaults for boilerplate generation.',
      goodAnswer: 'Pick the closest operating model (for cafes/restaurants choose Hospitality).',
      avoid: 'Avoid choosing a broad category when a more specific fit exists.',
    };
  }

  if (cardKind === 'sub_industry') {
    return {
      meaning: 'Adds operational context used by AI to fine-tune policy assumptions.',
      goodAnswer: 'Provide concrete detail like "smoothie shop with counter service".',
      avoid: 'Avoid vague notes like "food" or "service business".',
    };
  }

  if (cardKind === 'states') {
    return {
      meaning: 'Defines where statutory boilerplate must apply.',
      goodAnswer:
        mode === 'single_state'
          ? 'Select exactly one state where the handbook applies.'
          : 'Select every operating state you need coverage for.',
      avoid: 'Avoid omitting active states or selecting states with no workforce.',
    };
  }

  if (cardKind === 'legal_name') {
    return {
      meaning: 'This legal entity name appears in formal policy language.',
      goodAnswer: 'Use the exact registered legal entity name.',
      avoid: 'Avoid shorthand brands or nicknames in this field.',
    };
  }

  if (cardKind === 'dba') {
    return {
      meaning: 'Optional public-facing operating name shown alongside legal name.',
      goodAnswer: 'Enter DBA only if officially used in employee communications.',
      avoid: 'Avoid placeholder DBAs that are not actually used.',
    };
  }

  if (cardKind === 'ceo') {
    return {
      meaning: 'Executive signature/authority reference used in handbook metadata.',
      goodAnswer: 'Use current CEO/President full name.',
      avoid: 'Avoid outdated names or role titles only.',
    };
  }

  if (cardKind === 'headcount') {
    return {
      meaning: 'Provides context for policy assumptions and HR process language.',
      goodAnswer: 'Enter an approximate current employee count.',
      avoid: 'Avoid stale or intentionally rounded placeholder numbers.',
    };
  }

  if (cardKind === 'profile_bool' && profileKey) {
    return (
      PROFILE_BOOL_HELPER_COPY[profileKey] || {
        meaning: 'This signal determines whether corresponding policy language is included.',
        goodAnswer: 'Answer based on current real operating conditions.',
        avoid: 'Avoid aspirational or future-state answers.',
      }
    );
  }

  if (cardKind === 'policy_pack') {
    return {
      meaning: 'Generates baseline state/city boilerplate and unresolved follow-up prompts.',
      goodAnswer: 'Run this after scope/profile are accurate, then answer follow-ups clearly.',
      avoid: 'Avoid creating custom sections before required boilerplate is generated.',
    };
  }

  if (cardKind === 'guided_followup') {
    return {
      meaning: 'This answer fills a policy gap identified during guided generation.',
      goodAnswer: `Provide a concrete operational answer${
        guidedQuestionPlaceholder ? ` (e.g., ${guidedQuestionPlaceholder})` : ''
      }.`,
      avoid: 'Avoid vague answers like "TBD" for required follow-ups.',
    };
  }

  if (cardKind === 'custom_sections') {
    return {
      meaning: 'Adds employer-authored policies outside statutory boilerplate.',
      goodAnswer: 'Include only company-specific culture or process rules that counsel approves.',
      avoid: 'Avoid copying legal boilerplate into custom sections without review.',
    };
  }

  if (cardKind === 'upload') {
    return {
      meaning: 'Uploads the base handbook document for upload-mode workflows.',
      goodAnswer: 'Upload the latest approved handbook in PDF/DOC/DOCX/TXT format.',
      avoid: 'Avoid outdated drafts, scans with unreadable text, or unrelated files.',
    };
  }

  if (cardKind === 'review') {
    return {
      meaning: 'This is your final checkpoint before draft creation.',
      goodAnswer: 'Confirm title, scope, and workforce profile are accurate for current operations.',
      avoid: 'Do not publish if states, ownership details, or required follow-ups are incomplete.',
    };
  }

  return {
    meaning: 'This section collects required information for handbook generation.',
    goodAnswer: 'Provide current, specific, and operationally accurate input.',
    avoid: 'Avoid placeholders or assumptions that have not been verified.',
  };
}

function applyIndustryAndJurisdictionContext(
  base: WizardHelperCopy,
  context: WizardHelperContext
): WizardHelperCopy {
  const { sourceType, cardKind, industry, industryLabel, selectedStates } = context;
  if (sourceType !== 'template' || cardKind === 'source') {
    return base;
  }

  const pack = INDUSTRY_HELPER_PACKS[industry] || defaultIndustryPack(industryLabel);
  const normalizedStates = Array.from(new Set(selectedStates.map((state) => state.toUpperCase())));

  const jurisdictionNotes = normalizedStates
    .map((state) => JURISDICTION_HELPER_NOTES[state])
    .filter((note): note is string => Boolean(note));

  const stateOverlay = normalizedStates.reduce<Partial<WizardHelperCopy>>((acc, state) => {
    const overlay = pack.stateOverlays?.[state];
    if (!overlay) return acc;
    return {
      meaning: joinSentences(acc.meaning, overlay.meaning),
      goodAnswer: joinSentences(acc.goodAnswer, overlay.goodAnswer),
      avoid: joinSentences(acc.avoid, overlay.avoid),
    };
  }, {});

  return {
    meaning: joinSentences(base.meaning, pack.meaning, jurisdictionNotes.join(' '), stateOverlay.meaning),
    goodAnswer: joinSentences(base.goodAnswer, pack.goodAnswer, stateOverlay.goodAnswer),
    avoid: joinSentences(base.avoid, pack.avoid, stateOverlay.avoid),
  };
}

export function getWizardHelperCopy(context: WizardHelperContext): WizardHelperCopy {
  const base = resolveBaseCopy(context);
  return applyIndustryAndJurisdictionContext(base, context);
}
