# Paris, FR — Compliance Requirements

**Jurisdiction ID**: `3f052b69-a137-4a37-8739-f470e88467b3`
**Researched**: 2026-03-23
**Groups**: labor
**Categories researched**: 12
**Total requirements found**: 45

---

## 1. `minimum_wage` — Minimum Wage

### SMIC (Salaire Minimum Interprofessionnel de Croissance)
- **Regulation Key**: `national_minimum_wage`
- **Description**: The SMIC is France's national minimum wage, adjusted annually on January 1 based on consumer price index for lowest-income quintile and half the gain in average hourly wages. Mid-year automatic increase triggered if CPI rises 2%+ since last SMIC establishment. From 1 January 2026: EUR 12.02/hr gross (EUR 9.52 net), EUR 1,823.03/month gross (151.67 hours). Previous: EUR 11.88/hr from 1 November 2024. Mayotte exception: 87.5% of metropolitan rate.
- **Current Value**: EUR 12.02/hr gross; EUR 1,823.03/month gross (2026)
- **Numeric Value**: 12.02
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Effective Date**: 2026-01-01
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2300
- **Source Name**: Service-Public.gouv.fr

---

## 2. `overtime` — Overtime

### Overtime Pay Rates (Heures Supplémentaires)
- **Regulation Key**: `daily_weekly_overtime`
- **Description**: France's legal workweek is 35 hours (Code du travail L3121-27). Any hour above 35 is overtime. Default rates: hours 36-43 (first 8 OT hours) at +25% premium; hours 44+ at +50% premium. Collective agreements may set different rates with a minimum floor of +10%. Annual overtime cap: 220 hours per employee (default; collective agreements can adjust). Overtime pay is exempt from employee income tax up to EUR 7,500 net/year. From 2026, employer forfait deduction on OT contributions: EUR 1.50/hr (<20 employees), EUR 0.50/hr (20+ employees).
- **Current Value**: +25% (hours 36-43); +50% (hours 44+); 220 hr annual cap
- **Numeric Value**: 25
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2391
- **Source Name**: Service-Public.gouv.fr

### Maximum Working Hours
- **Regulation Key**: `mandatory_overtime_restrictions`
- **Description**: Maximum 10 hours/day (extendable to 12 by collective agreement or labor inspectorate authorization). Maximum 48 hours in any single week. Maximum 44 hours averaged over any 12 consecutive weeks (can be raised to 46 by collective agreement). Hours beyond the annual overtime cap (220 hours) trigger mandatory compensatory rest: 50% of excess hours for companies with ≤20 employees, 100% for companies with 21+ employees. Forfait jours for autonomous cadres: 218 working days/year (max 235 by agreement); approximately 9 JRS rest days in 2026.
- **Current Value**: 10 hrs/day max; 48 hrs/week absolute max; 44 hrs avg/12 weeks
- **Numeric Value**: 48
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F1911
- **Source Name**: Service-Public.gouv.fr

---

## 3. `sick_leave` — Sick Leave

### Statutory Sick Leave (Arrêt Maladie)
- **Regulation Key**: `statutory_sick_leave`
- **Description**: 3-day waiting period (délai de carence) — no payment for first 3 days. From day 4, Sécurité sociale (CPAM) pays 50% of daily base wage, capped at 1.4x SMIC (approx. EUR 2,522.57/month gross) since April 2025 reform. Maximum IJSS: EUR 41.47 gross/day. Medical certificate required within 48 hours. Employer top-up (maintien de salaire) after 7-day employer waiting period for employees with 1+ year seniority: 30 days at 90% gross + 30 days at 66.66% (base; increases by 10 days per tier for each 5 years of additional seniority, up to 90 days each at 31+ years). Employer supplement includes IJSS — employer pays the difference.
- **Current Value**: 50% of daily wage from day 4 (capped at 1.4x SMIC); employer tops up to 90% then 66%
- **Numeric Value**: 50
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F3053
- **Source Name**: Service-Public.gouv.fr

---

## 4. `leave` — Leave

### Statutory Annual Leave (Congés Payés)
- **Regulation Key**: `annual_leave_entitlement`
- **Description**: 2.5 working days per month worked = 30 working days (5 weeks) per year. France counts Saturdays as working days (jours ouvrables). Acquisition period: June 1 to May 31. Main holiday period (congé principal): May 1 to October 31 — must take at least 12 continuous days (2 weeks). Maximum 24 consecutive days (4 weeks). Fractionnement bonus: 1 extra day for 3-5 days taken outside summer; 2 extra days for 6+ days outside summer. RTT days (for employees working >35 hrs): approximately 8-10 extra days/year depending on hours. RTT monetization extended through December 31, 2026 at overtime rate +10% minimum.
- **Current Value**: 30 working days (5 weeks) per year + fractionnement bonus days + RTT
- **Numeric Value**: 30
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Paid**: True
- **Max Weeks**: 5
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2258
- **Source Name**: Service-Public.gouv.fr

### Maternity Leave (Congé de Maternité)
- **Regulation Key**: `statutory_maternity_leave`
- **Description**: Duration varies by child count: 1st/2nd child 16 weeks (6 prenatal + 10 postnatal); 3rd+ child 26 weeks (8+18); twins 34 weeks (12+22); triplets+ 46 weeks (24+22). Minimum mandatory: 8 weeks total, 6 weeks postnatal. Up to 3 weeks prenatal transferable to postnatal (with medical approval). Daily allowance (IJSS) from CPAM: average of last 3 months gross / 91.25, minus 21% social deductions. Capped at Social Security ceiling (EUR 4,005/month in 2026). Max IJSS ~EUR 104/day. NEW for 2026 (PLFSS 2026): supplementary birth leave of 1-2 additional months for either parent.
- **Current Value**: 16 weeks (1st/2nd child); 26 weeks (3rd+); 34 weeks (twins)
- **Numeric Value**: 16
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Paid**: True
- **Max Weeks**: 16
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2265
- **Source Name**: Service-Public.gouv.fr

### Paternity Leave (Congé de Paternité)
- **Regulation Key**: `statutory_paternity_leave`
- **Description**: Since July 1, 2021: 3-day birth leave (employer-paid, mandatory) + 25 calendar days paternity leave (32 for multiple births). Total: 28 days (single) / 35 days (multiple). First 4 days of paternity leave are mandatory — employer prohibited from employing father. Remaining 21 days (28 for multiples) can be split into max 2 periods of 5+ days each, within 6 months of birth. Paid by Sécurité sociale as IJSS (same calculation as maternity). NEW for 2026: supplementary birth leave of 1-2 additional months (PLFSS 2026).
- **Current Value**: 28 calendar days total (single birth); 35 days (multiple)
- **Numeric Value**: 28
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Paid**: True
- **Max Weeks**: 4
- **Effective Date**: 2021-07-01
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F3156
- **Source Name**: Service-Public.gouv.fr

### Statutory Notice Periods
- **Regulation Key**: `statutory_notice_period_employer`
- **Description**: Dismissal notice (Code du travail L1234-1): less than 6 months seniority — set by collective agreement/contract/custom (no statutory minimum); 6 months to 2 years — 1 month; 2+ years — 2 months. Cadres (managers): virtually all collective agreements set 3 months regardless of seniority. Resignation: no statutory period; set by convention collective (typically 1 month non-cadres, 3 months cadres). No notice required for gross misconduct (faute grave) or willful wrongdoing (faute lourde). Employer may waive notice but must pay indemnité compensatrice de préavis.
- **Current Value**: 1 month (6mo-2yr); 2 months (2yr+); 3 months (cadres by CBA)
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.legifrance.gouv.fr/codes/section_lc/LEGITEXT000006072050/LEGISCTA000006189443/
- **Source Name**: Légifrance

### Severance Pay (Indemnité de Licenciement)
- **Regulation Key**: `severance_pay`
- **Description**: Minimum 8 months continuous service on CDI (permanent contract). Not applicable for faute grave/lourde. Legal minimum: 1/4 month salary per year of service for first 10 years; 1/3 month per year beyond 10 years. Reference salary: most favorable of last 12 months average or last 3 months average (with bonuses prorated). Partial years prorated. Tax exempt up to EUR 288,360 (2026). Convention collective may provide more (e.g., metallurgy commonly offers 1/3 or 1/2 month from year 1). Rupture conventionnelle (agreed termination) must pay at least the legal severance.
- **Current Value**: 1/4 month per year (first 10 years); 1/3 month per year (beyond 10 years)
- **Numeric Value**: 0.25
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://entreprendre.service-public.gouv.fr/vosdroits/F987
- **Source Name**: Service-Public.gouv.fr

### Bereavement and Family Event Leave
- **Regulation Key**: `bereavement_leave`
- **Description**: Fully paid, no seniority requirement. Death of spouse/PACS partner/cohabiting partner: 3 days. Death of parent/parent-in-law/sibling: 3 days. Death of child 25+: 5 days. Death of child under 25: 7 days + 8 days congé de deuil (15 total, can be split into 2 periods within 1 year). Marriage: 4 days. PACS: 4 days. Birth/adoption: 3 days. Marriage of child: 1 day. Announcement of child disability: 5 days. Convention collective may provide more but never less.
- **Current Value**: 3-15 days depending on event (all paid)
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Paid**: True
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2278
- **Source Name**: Service-Public.gouv.fr

---

## 5. `meal_breaks` — Meal & Rest Breaks

### Break and Rest Periods
- **Regulation Key**: `meal_break`
- **Description**: 20 minutes minimum break once daily work reaches 6 continuous hours (Code du travail L3121-16). Collective agreements may provide longer. No separate "meal break" law — the 20-minute break is the statutory minimum. For minors (under 18): 30-minute break after 4.5 consecutive hours.
- **Current Value**: 20 minutes per 6 hours of work
- **Numeric Value**: 20
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F1911
- **Source Name**: Service-Public.gouv.fr

### Daily and Weekly Rest
- **Regulation Key**: `rest_break`
- **Description**: Daily rest: 11 consecutive hours minimum between two working days (L3131-1; derogation possible but never below 9 hours). Weekly rest: 24 consecutive hours minimum per week, given on Sunday as a rule. Combined with daily rest: 35 consecutive hours minimum (24+11). Sunday work requires specific authorization or sector exemption.
- **Current Value**: 11 hours daily rest; 35 hours weekly rest (24+11)
- **Numeric Value**: 11
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2327
- **Source Name**: Service-Public.gouv.fr

---

## 6. `final_pay` — Final Pay

### Solde de Tout Compte (Final Settlement)
- **Regulation Key**: `final_pay_termination`
- **Description**: Three mandatory documents on last day of work: (1) Certificat de travail (work certificate — dates, positions, portability of insurance rights); (2) Solde de tout compte (itemized final settlement — prorated salary, unused leave at 10% of gross or actual salary, severance if applicable, notice indemnity, bonuses/commissions); (3) Attestation France Travail (for unemployment benefits, transmitted electronically via DSN). Delay beyond 8 days is considered harmful per case law and can result in damages via Conseil de Prud'hommes. If employee signs the solde: 6 months to contest. Unsigned: up to 3 years for salary disputes.
- **Current Value**: All documents and final pay due on last day of work
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://entreprendre.service-public.gouv.fr/vosdroits/F86
- **Source Name**: Service-Public.gouv.fr

### Final Pay on Resignation
- **Regulation Key**: `final_pay_resignation`
- **Description**: Same rules as termination — solde de tout compte, certificat de travail, and attestation France Travail must be issued on the last day of employment (end of notice period). Includes prorated salary, accrued unused congés payés (calculated as 10% of gross remuneration or actual salary, whichever is higher), any RTT days owed, prorated bonuses. Notice period indemnity applies only if employer waives the notice.
- **Current Value**: Due on last day of employment
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://entreprendre.service-public.gouv.fr/vosdroits/F21789
- **Source Name**: Service-Public.gouv.fr

---

## 7. `pay_frequency` — Pay Frequency

### Monthly Payment (Mensualisation)
- **Regulation Key**: `standard_pay_frequency`
- **Description**: Wages must be paid once per month on a fixed date (Code du travail L3242-1). Monthly salary = hourly rate x 151.67 hours (35 hrs/week x 52/12). Employees may request an advance for work already performed. Itemised payslip (bulletin de paie) mandatory with: employer/employee ID, SIRET, convention collective, pay period, hours worked (normal vs OT), gross salary, itemized social contributions, prélèvement à la source (income tax withholding since 2019), montant net social (since July 2023), net pay, leave balance. Electronic payslips allowed by default since 2017; employee may opt for paper. Digital payslips accessible for 50 years or until age 75. Penalties: EUR 750-7,500 per violation for incorrect payslips.
- **Current Value**: Monthly; itemised payslip required
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F559
- **Source Name**: Service-Public.gouv.fr

---

## 8. `scheduling_reporting` — Scheduling & Reporting Time

### Working Time Framework
- **Regulation Key**: `predictive_scheduling`
- **Description**: France has no US-style predictive scheduling law, but the 35-hour legal workweek framework is highly structured. Employers must communicate work schedules to employees. Any change to working hours is a modification of the employment contract requiring employee consent (unless collective agreement provides otherwise). Forfait jours employees (218 days/year) track days not hours. Employers must maintain accurate records of working hours. CSE must be consulted before any working time changes in companies with 50+ employees. RTT system compensates employees working above 35 hours with rest days rather than overtime pay.
- **Current Value**: 35-hour legal workweek; schedule changes require consent or CBA
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F1911
- **Source Name**: Service-Public.gouv.fr

---

## 9. `workers_comp` — Workers' Comp

### Accident du Travail / Maladie Professionnelle (AT/MP)
- **Regulation Key**: `mandatory_coverage`
- **Description**: No-fault employer-funded workers' compensation. Employer AT/MP rate varies by industry risk classification and company size: national average 2.08% (2026). Under 20 employees: collective (sectoral) rate; 20-149: mixed rate; 150+: individual rate based on company accident history. Range ~0.9% to 6%+. Benefits: 100% medical coverage (no co-pay), daily allowances from day 1 (no waiting period unlike ordinary sick leave): days 2-28 at 60% of daily salary (max ~EUR 240/day), day 29+ at 80% (max ~EUR 320/day). Permanent disability: pension based on disability rate. Death: funeral allowance + survivor's pension (40% to spouse, 25% per child). Enhanced claims possible for employer's faute inexcusable.
- **Current Value**: Employer rate avg 2.08% (varies 0.9%-6%+); 100% medical; 60-80% salary replacement
- **Numeric Value**: 2.08
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.ameli.fr/assure/remboursements/accident-travail
- **Source Name**: Ameli.fr (CPAM)

### Employer Social Charges (Cotisations Patronales)
- **Regulation Key**: `social_insurance_employer`
- **Description**: Total employer social contributions approximately 40-45% on top of gross salary. Major components (2026): Assurance maladie 7-13% (total salary); Allocations familiales 3.45-5.25% (total salary); Vieillesse plafonnée 8.55% (up to 1x PMSS EUR 4,005/month); Vieillesse déplafonnée 2.11% (total salary, up from 2.02%); Assurance chômage 4.05% (up to 4x PMSS; bonus-malus range 2.95-5%); AGS 0.25%; AGIRC-ARRCO T1 4.72% (up to PMSS), T2 12.95% (1-8x PMSS); CEG 1.29%/1.62%; Formation professionnelle 0.55-1%; Taxe d'apprentissage 0.68%; AT/MP variable; FNAL 0.10-0.50%. Reduced rates (RGDU) apply for salaries near SMIC. Social Security monthly ceiling (PMSS): EUR 4,005 (2026).
- **Current Value**: ~40-45% of gross salary; PMSS EUR 4,005/month (2026)
- **Numeric Value**: 42
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Effective Date**: 2026-01-01
- **Source URL**: https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html
- **Source Name**: Urssaf

### Employee Social Charges (Cotisations Salariales)
- **Regulation Key**: `social_insurance_employee`
- **Description**: Total employee deductions approximately 22-25% of gross salary. CSG 9.2% (on 98.25% of gross up to 4x PMSS; 6.8% deductible, 2.4% non-deductible); CRDS 0.5% (non-deductible); Vieillesse plafonnée 6.90% (up to PMSS); Vieillesse déplafonnée 0.40% (total salary); AGIRC-ARRCO T1 3.15%, T2 8.64%; CEG T1 0.86%, T2 1.08%; APEC 0.024% (cadres only). Employee unemployment contributions eliminated in 2018. 2026 change: CSG on capital income increased to 10.6% (total social levies on capital gains 31.4%).
- **Current Value**: ~22-25% of gross salary
- **Numeric Value**: 23
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.cleiss.fr/docs/regimes/regime_france/an_a2.html
- **Source Name**: CLEISS

---

## 10. `workplace_safety` — Workplace Safety

### Obligation de Sécurité and DUERP
- **Regulation Key**: `osha_general_duty`
- **Description**: Code du travail Part IV (L4121-1 et seq.): employer has obligation de sécurité de résultat — near-absolute duty to ensure worker safety. 9 general prevention principles (L4121-2). DUERP (Document Unique d'Évaluation des Risques Professionnels) mandatory for ALL employers from first employee: must list and assess all occupational risks per work unit. Update annually for 11+ employees; upon any significant change for all. Since 2023: must include programme annuel de prévention (50+ employees). Since 2025: must be digital. Retained 40 years. Penalties: EUR 1,500 per work unit lacking evaluation. Inspection du travail enforces with broad powers (enter without notice, issue notices, order stoppages). Obstructing inspector: 1 year imprisonment + EUR 37,500 fine.
- **Current Value**: DUERP mandatory for all employers; obligation de résultat
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: True
- **Source URL**: https://entreprendre.service-public.gouv.fr/vosdroits/F35360
- **Source Name**: Service-Public.gouv.fr

---

## 11. `anti_discrimination` — Anti-Discrimination

### Protected Grounds (Code du Travail L1132-1)
- **Regulation Key**: `protected_classes`
- **Description**: France has 25+ protected grounds under Code du travail L1132-1, among the most extensive globally: origin, sex, morals/customs, sexual orientation, gender identity, age, family situation, pregnancy, genetic characteristics, economic vulnerability, ethnicity, alleged race, nation, political opinions, trade union activities, mutual benefit activities, local political mandate, religious beliefs, physical appearance, surname, place of residence, bank domiciliation, health condition, disability/loss of autonomy, ability to speak language other than French, whistleblower status. Enforcement by Défenseur des droits (can impose penalties up to EUR 15,000 for legal entities). Burden of proof shifts to employer once claimant presents suggestive facts.
- **Current Value**: 25+ protected grounds
- **Numeric Value**: 25
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000045391841
- **Source Name**: Légifrance

### Gender Pay Equality Index (Index de l'Égalité Professionnelle)
- **Regulation Key**: `pay_transparency`
- **Description**: Mandatory for companies with 50+ employees (Loi Avenir Professionnel, 2018). 100-point scale across 4-5 indicators: pay gap (40 pts), raise distribution gap (20 pts), % women raised after maternity (15 pts), under-represented sex in top 10 paid (10 pts). Publication deadline: March 1 each year. Score below 75: must publish corrective measures and achieve 75+ within 3 years. Below 85: must set improvement targets. Penalty for non-publication or persistent failure: up to 1% of total annual payroll. Published on company website and reported via Egapro platform.
- **Current Value**: Mandatory 100-point index for 50+ employees; min score 75
- **Numeric Value**: 50
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: True
- **Effective Date**: 2019-03-01
- **Source URL**: https://www.economie.gouv.fr/entreprises/index-egalite-professionnelle-obligatoire
- **Source Name**: Ministère de l'Économie

### Whistleblower Protection
- **Regulation Key**: `whistleblower_protection`
- **Description**: Loi Sapin II (2016) as strengthened by Loi du 21 mars 2022 (transposing EU Whistleblower Directive). Whistleblower status is a protected ground under L1132-1. Companies with 50+ employees must establish internal reporting channels. External reporting to authorities possible without first using internal channels. Protection against retaliation (dismissal, demotion, harassment). Burden of proof on employer to show actions unrelated to disclosure. Whistleblower identity confidential.
- **Current Value**: Protected ground; internal channels mandatory for 50+ employees
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: True
- **Effective Date**: 2022-09-01
- **Source URL**: https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000045391841
- **Source Name**: Légifrance

---

## 12. `minor_work_permit` — Minor Work Permits

### Child and Young Worker Restrictions
- **Regulation Key**: `work_permit`
- **Description**: General minimum working age: 16 (end of compulsory schooling). Exceptions: age 15 for apprenticeships (if completed collège); age 14-15 for light work during school holidays only (with labor inspectorate authorization, max half of holiday period); under 14 for entertainment/modeling only (prefectural authorization). Written parental consent required. Employer must request inspectorate authorization 15 days before start for 14-15 year-olds.
- **Current Value**: Minimum age 16; exceptions from 14 (light work) and 15 (apprenticeship)
- **Numeric Value**: 16
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F1649
- **Source Name**: Service-Public.gouv.fr

### Hour Limits for Minors
- **Regulation Key**: `hour_limits_14_15`
- **Description**: Age 14-15 (school holidays): max 7 hours/day, 32-35 hours/week. Age 16-17: max 8 hours/day, 35 hours/week. Rest: 14 consecutive hours for under 16; 12 hours for 16-17. Weekly rest: 2 consecutive days. Break: 30 minutes after 4.5 consecutive hours. No work on public holidays (limited exceptions). Night work prohibited: under 16 between 8pm-6am; 16-17 between 10pm-6am (exceptions for bakery apprentices from 4am, entertainment with authorization). Dangerous work prohibited for minors (D4153-15); derogation possible for apprentices 15+ with authorization and medical clearance. Penalties: EUR 1,500 fine; exploitation: up to 5 years imprisonment + EUR 75,000 fine.
- **Current Value**: Under 16: max 7 hrs/day; 16-17: max 8 hrs/day, 35 hrs/week
- **Numeric Value**: 7
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F1688
- **Source Name**: Service-Public.gouv.fr

---

## 13. `fr_specific` — France-Specific Provisions

### Mandatory Complementary Health Insurance (Mutuelle d'Entreprise)
- **Regulation Key**: `fr_mutuelle_obligation`
- **Description**: Since January 1, 2016, ALL private-sector employers must provide collective complementary health insurance (mutuelle) to ALL employees. Employer must pay at least 50% of premium. Plan must be "responsible and solidarity-based" (contrat responsable). Minimum coverage basket (panier de soins minimum): 100% ticket modérateur reimbursement, hospital daily surcharge (EUR 20/day) with no duration limit, dental at 125% of SS base tariff (100% Santé for certain prostheses), optical EUR 100-150 for lenses+frame (renewal every 2 years). Employee opt-out possible if: covered by spouse's plan, on CDD <3 months, or contribution exceeds 10% of salary for part-timers.
- **Current Value**: Mandatory; employer pays ≥50% of premium
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: True
- **Effective Date**: 2016-01-01
- **Source URL**: https://entreprendre.service-public.gouv.fr/vosdroits/F33754
- **Source Name**: Service-Public.gouv.fr

### Prévoyance (Death/Disability Insurance for Cadres)
- **Regulation Key**: `fr_prevoyance_cadres`
- **Description**: ANI of November 17, 2017 (replacing 1947 convention). Mandatory for all cadres: employer must subscribe to collective prévoyance and contribute minimum 1.50% of Tranche 1 salary (up to 1x PASS = EUR 48,060/year in 2026). Contribution exclusively borne by employer. At least 0.76% must cover death benefit (capital décès). Remainder can cover disability/incapacity. Non-compliance penalty: employer must pay heirs 3x annual PASS (EUR 144,180 in 2026). Most industry collective agreements extend prévoyance to all employees (not just cadres), typically with 50/50 or 60/40 employer/employee split.
- **Current Value**: 1.50% of T1 salary minimum (employer-only); penalty 3x PASS for non-compliance
- **Numeric Value**: 1.5
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: True
- **Source URL**: https://www.legifrance.gouv.fr/conv_coll/id/KALITEXT000036732007/
- **Source Name**: Légifrance

### CSE (Comité Social et Économique)
- **Regulation Key**: `fr_cse_worker_representation`
- **Description**: Mandatory for 11+ employees (maintained 12 consecutive months). At 50+ employees: gains legal personality, operating budget (0.20% of gross payroll, 0.22% for 2,000+), social/cultural budget. Three mandatory annual consultations (strategic orientations, economic situation, social policy). Must be consulted before collective redundancies, restructuring, working time changes, new technology. At 300+: CSSCT (health/safety commission) mandatory, meets quarterly, minimum 3 members. CSE members receive delegation hours (10-12 hrs/month at 11-49 employees). Employer failure to organize elections: criminal offence.
- **Current Value**: Mandatory at 11+ employees; expanded at 50+ and 300+
- **Numeric Value**: 11
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Effective Date**: 2018-01-01
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F34474
- **Source Name**: Service-Public.gouv.fr

### Mandatory Profit Sharing (Participation)
- **Regulation Key**: `fr_participation_profit_sharing`
- **Description**: Mandatory for companies with 50+ employees (Code du travail L3321-1). NEW since Jan 2025 (Loi Partage de la Valeur): companies with 11-49 employees must also implement value-sharing if net profit ≥1% of turnover for 3 consecutive years. Legal formula: RSP = 1/2 x (B - 5% x C) x (S / VA). Amounts blocked for 5 years (early release for life events). Tax advantages: exempt from income tax if placed in savings plan (capped EUR 36,045 in 2026); exempt from employer social contributions. Optional intéressement (performance bonus) also available for all companies, capped at 75% of PASS per employee. Value-sharing bonus (PPV): up to EUR 3,000/employee (EUR 6,000 with participation/intéressement).
- **Current Value**: Mandatory at 50+ employees; NEW at 11-49 if profit ≥1% turnover x 3 years
- **Numeric Value**: 50
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: True
- **Effective Date**: 2025-01-01
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F2141
- **Source Name**: Service-Public.gouv.fr

### Navigo Transport Reimbursement (Île-de-France)
- **Regulation Key**: `fr_transport_reimbursement`
- **Description**: Code du travail L3261-2: all employers must reimburse 50% of employees' public transport pass. Particularly impactful in Paris/Île-de-France where the Navigo pass costs approximately EUR 86.40/month. Employer reimbursement is exempt from social charges and income tax. Also applies to other sustainable transport (vélo, covoiturage) via the forfait mobilités durables (up to EUR 800/year, combinable with Navigo reimbursement up to EUR 900/year total tax-free).
- **Current Value**: 50% of Navigo pass (~EUR 43.20/month); forfait mobilités durables up to EUR 800/year
- **Numeric Value**: 50
- **Jurisdiction Level**: national
- **Jurisdiction Name**: France
- **Requires Written Policy**: False
- **Source URL**: https://www.service-public.gouv.fr/particuliers/vosdroits/F19846
- **Source Name**: Service-Public.gouv.fr
