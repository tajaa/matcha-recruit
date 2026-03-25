# London, GB — Manufacturing Compliance Research

**Researched by**: Claude Code (web search)
**Date**: 2026-03-24
**Industry**: General manufacturing

---

## Manufacturing

### process_safety

#### COMAH Regulations 2015 (Major Accident Hazards)
- **regulation_key**: `osha_psm`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Control of Major Accident Hazards Regulations 2015
- **description**: COMAH implements the Seveso III Directive. Applies to establishments holding dangerous substances above threshold quantities in Schedule 1. Lower-tier sites must prepare a Major Accident Prevention Policy (MAPP). Upper-tier sites must prepare a detailed Safety Report. All sites must take all measures necessary to prevent major accidents and limit consequences. Joint enforcement by HSE and Environment Agency.
- **current_value**: Lower-tier: MAPP required. Upper-tier: full Safety Report + emergency plan required
- **source_url**: https://www.hse.gov.uk/comah/comah15.htm
- **source_name**: HSE — COMAH 2015
- **requires_written_policy**: true

#### Process Hazard Analysis (COMAH Safety Report)
- **regulation_key**: `process_hazard_analysis`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: COMAH Safety Report — Hazard Identification and Risk Assessment
- **description**: Upper-tier COMAH sites must submit a Safety Report including identification of major accident hazards, risk assessment, demonstration that adequate safety measures exist, and emergency response planning. Must be reviewed and updated at least every 5 years or after any significant modification.
- **current_value**: Safety Report required for upper-tier sites; review every 5 years
- **source_url**: https://www.hse.gov.uk/pubns/books/l111.htm
- **source_name**: HSE — Guide to COMAH Regulations
- **requires_written_policy**: true

#### Emergency Action Plan (COMAH)
- **regulation_key**: `emergency_action_plan`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: COMAH On-Site and Off-Site Emergency Plans
- **description**: Upper-tier COMAH operators must prepare an internal emergency plan. Local authorities must prepare an external emergency plan for the surrounding area. Plans must be tested at suitable intervals not exceeding 3 years.
- **current_value**: Internal + external emergency plans; tested every 3 years
- **source_url**: https://www.hse.gov.uk/comah/index.htm
- **source_name**: HSE — COMAH
- **requires_written_policy**: true

### environmental_compliance

#### UK Environmental Permit
- **regulation_key**: `air_quality_permit`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Environmental Permit for Industrial Emissions
- **description**: Manufacturing facilities producing emissions to air, water, or land require an Environmental Permit. Large installations regulated by Environment Agency. Medium/smaller sites regulated by local authorities (City of London for London sites). Must apply Best Available Techniques (BAT) to prevent or minimise emissions. UK's new BAT framework (2025) enables regulators and industry to set challenging emission reduction standards.
- **current_value**: Environmental Permit required; BAT standards apply
- **source_url**: https://www.gov.uk/guidance/check-if-you-need-an-environmental-permit
- **source_name**: GOV.UK — Environmental Permits
- **requires_written_policy**: false

#### Emissions Reporting
- **regulation_key**: `emissions_reporting`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: UK Emissions Reporting and Air Quality Standards
- **description**: Air Quality Standards Regulations 2010 (as amended) set limit values for NO2, particulate matter, and ozone. Facilities must conduct air emissions risk assessments using Environment Agency methodology. Must derive Environmental Assessment Levels (EALs) for substances emitted. 2025 updates include new EAL derivation methods.
- **current_value**: Air emissions risk assessment required; comply with Air Quality Standards Regulations 2010
- **source_url**: https://www.gov.uk/guidance/air-emissions-risk-assessment-for-your-environmental-permit
- **source_name**: GOV.UK — Air Emissions Risk Assessment
- **requires_written_policy**: false

### chemical_safety

#### COSHH Regulations 2002
- **regulation_key**: `hazcom_ghs`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Control of Substances Hazardous to Health Regulations 2002 (COSHH)
- **description**: Requires employers to assess risks from hazardous substances (Regulation 6), prevent or control exposure (Regulation 7), and provide information/instruction/training (Regulation 12). Covers liquids, solids, fumes, dust, vapours, fibres, nano-particles, mists, gases, and biological agents. Risk assessments must be site-specific, current, and communicated to staff. HSE signals tighter monitoring and tougher penalties for breaches in manufacturing sectors.
- **current_value**: COSHH risk assessment + control measures + training required for all hazardous substances
- **source_url**: https://www.hse.gov.uk/coshh/
- **source_name**: HSE — COSHH
- **requires_written_policy**: true

#### UK REACH
- **regulation_key**: `sds_management`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: UK REACH — Registration, Evaluation, Authorisation and Restriction of Chemicals
- **description**: Post-Brexit UK REACH (retained from EU REACH 1907/2006) requires manufacturers and importers of chemicals to evaluate and manage risks. Safety Data Sheets (SDS) required in 16-section format. Cross-government PFAS Plan to be published 2026, with 2027 decision on restricting PFAS in firefighting foams under UK REACH. HSE acts as implementing authority for chemicals regulation.
- **current_value**: UK REACH registration + SDS required; PFAS restrictions forthcoming 2026-2027
- **source_url**: https://www.hse.gov.uk/chemicals/guidance.htm
- **source_name**: HSE — Chemical Safety Guidance
- **requires_written_policy**: false

#### Hazardous Substance Storage
- **regulation_key**: `hazardous_substance_storage`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Hazardous Substance Storage Requirements
- **description**: Chemical storage must comply with environmental legislation including the Environmental Permitting Regulations, Water Resources Act 1991, and Control of Pollution Act 1974. Bunding required for stored chemicals. Secondary containment for drums and IBCs. Specific requirements for flammable liquids under Dangerous Substances and Explosive Atmospheres Regulations 2002 (DSEAR).
- **current_value**: Bunding + secondary containment + DSEAR compliance for flammable storage
- **source_url**: https://www.hse.gov.uk/comah/guidance.htm
- **source_name**: HSE — Chemical Safety
- **requires_written_policy**: false

### machine_safety

#### PUWER 1998 (Provision and Use of Work Equipment)
- **regulation_key**: `machine_guarding`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Provision and Use of Work Equipment Regulations 1998 (PUWER)
- **description**: Places duties on owners, operators, and controllers of work equipment. Requires suitability assessment, safe condition maintenance, inspection at suitable intervals, and use of protective devices, controls, markings, and warning devices. Requires means of isolation from energy sources (UK equivalent of lockout/tagout, though LOTO is not separately enforced — isolation under PUWER is the legal requirement).
- **current_value**: Equipment suitability + guarding + energy isolation + inspection required
- **source_url**: https://www.hse.gov.uk/work-equipment-machinery/puwer.htm
- **source_name**: HSE — PUWER
- **requires_written_policy**: false

#### Lockout/Tagout (Energy Isolation under PUWER)
- **regulation_key**: `lockout_tagout`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Energy Isolation Requirements (PUWER Regulation 19)
- **description**: PUWER requires that work equipment is provided with a suitable means to isolate it from all its sources of energy, and that reconnection does not expose any person to risk. While formal LOTO is not separately enforced in the UK as in the US, isolation procedures under PUWER are mandatory and LOTO is recognised as best practice by HSE. Manufacturing sites typically implement LOTO voluntarily.
- **current_value**: Energy isolation means required under PUWER; LOTO is HSE best practice
- **source_url**: https://www.hse.gov.uk/work-equipment-machinery/
- **source_name**: HSE — Equipment and Machinery
- **requires_written_policy**: true

#### LOLER 1998 (Lifting Equipment)
- **regulation_key**: `crane_hoist_safety`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Lifting Operations and Lifting Equipment Regulations 1998 (LOLER)
- **description**: Applies to all lifting equipment including cranes, hoists, forklifts, and lifting accessories. Requires that lifting operations are planned, supervised, and carried out safely. Thorough examination required: every 6 months for equipment lifting persons, every 12 months for other lifting equipment, or in accordance with an examination scheme.
- **current_value**: Thorough examination every 6 months (persons) or 12 months (other); planned lifting operations
- **source_url**: https://www.hse.gov.uk/work-equipment-machinery/loler.htm
- **source_name**: HSE — LOLER
- **requires_written_policy**: true

### industrial_hygiene

#### Noise at Work Regulations 2005
- **regulation_key**: `noise_exposure`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Control of Noise at Work Regulations 2005
- **description**: Three threshold levels: Lower Exposure Action Value 80 dB(A) — assess risk, provide information/training. Upper Exposure Action Value 85 dB(A) — provide hearing protection, designate hearing protection zones. Exposure Limit Value 87 dB(A) taking account of hearing protection — must not be exceeded. Employers must reduce noise exposure through engineering/admin controls first, PPE as last resort. HSE updated guidance March 2025.
- **current_value**: Lower action 80 dB(A); upper action 85 dB(A); limit 87 dB(A) — stricter than US OSHA
- **source_url**: https://www.hse.gov.uk/noise/regulations.htm
- **source_name**: HSE — Noise Regulations
- **requires_written_policy**: true

#### Workplace Exposure Limits (WELs)
- **regulation_key**: `permissible_exposure_limits`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: UK Workplace Exposure Limits (EH40)
- **description**: UK WELs are published in HSE document EH40. Generally more stringent than US OSHA PELs. COSHH Regulation 7 requires exposure to be controlled to below the WEL. For substances without a WEL, exposure must be controlled to as low as reasonably practicable (ALARP). Updated periodically — manufacturers must check EH40 for current limits on chemicals used in their processes.
- **current_value**: WELs in EH40 — generally more stringent than US PELs
- **source_url**: https://www.hse.gov.uk/coshh/
- **source_name**: HSE — COSHH
- **requires_written_policy**: false

### trade_compliance

#### UKCA / CE Marking
- **regulation_key**: `customs_tariff`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: UKCA and CE Marking Requirements (Post-Brexit)
- **description**: Products placed on the GB market may use either UKCA or CE marking. Government laid legislation to continue recognition of CE marking indefinitely for most product categories. UKCA marking can be placed on a label or accompanying document until December 31, 2025; on product itself or label until December 31, 2027. Northern Ireland requires CE marking (EU single market member). Different rules for medical devices, construction products, and marine equipment.
- **current_value**: CE and UKCA both accepted in GB; UKCA label deadline Dec 2027
- **source_url**: https://www.gov.uk/guidance/using-the-ukca-marking
- **source_name**: GOV.UK — UKCA Marking
- **requires_written_policy**: false

### product_safety

*UK accepts CE marking and UKCA marking for products placed on the GB market. Tire-specific standards follow UNECE R117 (noise, wet grip, rolling resistance). Product safety covered under the Consumer Rights Act 2015 and General Product Safety Regulations 2005. No UK-specific requirements beyond the trade_compliance section above.*

### labor_relations

#### Employment Rights Act 2025 — Trade Union Recognition
- **regulation_key**: `collective_bargaining`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Employment Rights Act 2025 — Trade Union Recognition Reforms
- **description**: Major reforms to union recognition and collective bargaining. Recognition ballot threshold reduced: removes requirement for 40% of bargaining unit to vote in favour, only requiring a simple majority of those who vote. Membership threshold may be reduced to 2-10% (down from 10%). Employers must provide worker information within 5 working days of CAC notification. New 20-working-day window for access agreement negotiations. Union officers gain right to request workplace access. Workers gain stronger protections against dismissal for industrial action. Employers must provide written statement of right to join a union at start of employment. Expected implementation October 2026.
- **current_value**: Easier union recognition from Oct 2026; employer must notify right to join union
- **source_url**: https://www.acas.org.uk/employment-rights-act-2025
- **source_name**: ACAS — Employment Rights Act 2025
- **requires_written_policy**: true

#### Works Council / Employee Representation
- **regulation_key**: `works_council`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Information and Consultation of Employees Regulations
- **description**: ICE Regulations give employees in organisations with 50+ staff the right to be informed and consulted about matters that affect them. Post-Brexit, UK retains the framework for employee information and consultation. The Employment Rights Act 2025 further strengthens these rights.
- **current_value**: ICE rights apply to organisations with 50+ employees
- **source_url**: https://www.acas.org.uk/employment-rights-act-2025
- **source_name**: ACAS — Employment Rights Act 2025
- **requires_written_policy**: false

---

## General Labor

### minimum_wage

#### UK National Living Wage
- **regulation_key**: `state_minimum_wage`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: National Living Wage / National Minimum Wage
- **description**: National Living Wage (21+): £12.71/hour from April 2026 (up from £12.21). 18-20 rate: £10.85/hour. 16-17 rate: £8.00/hour. Apprentice rate: £7.55/hour. Enforced by HMRC and from April 2026 by the new Fair Work Agency.
- **current_value**: £12.71/hr (21+) from April 2026; Fair Work Agency enforcement begins
- **source_url**: https://www.lewissilkin.com/insights/2026/03/19/employment-law-changes-in-april-2026
- **source_name**: Lewis Silkin — Employment Law Changes April 2026
- **requires_written_policy**: false

### overtime

*No statutory overtime premium in the UK. Employees must not work more than 48 hours per week on average (Working Time Regulations 1998), but can opt out individually. No mandatory overtime pay rate — overtime terms are contractual.*

### sick_leave

#### Statutory Sick Pay
- **regulation_key**: `state_paid_sick_leave`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: UK Statutory Sick Pay (SSP)
- **description**: SSP increases to £123.25/week from April 2026. Major change: SSP payable from the first day of illness (previously fourth day) starting April 2026. Lower earnings limit for eligibility is being removed. Enforced by the new Fair Work Agency from April 2026.
- **current_value**: £123.25/week from day 1 of illness (April 2026); lower earnings limit removed
- **source_url**: https://www.acas.org.uk/checking-sick-pay/statutory-sick-pay-ssp
- **source_name**: ACAS — Statutory Sick Pay
- **requires_written_policy**: false

### leave

#### Statutory Holiday Entitlement
- **regulation_key**: `state_family_leave`
- **jurisdiction_level**: national
- **jurisdiction_name**: United Kingdom
- **title**: Statutory Annual Leave Entitlement
- **description**: All employees and workers legally entitled to minimum 28 days paid holiday per year (5.6 weeks). Employers can include bank holidays within this entitlement. Fair Work Agency gains enforcement powers for holiday pay compliance from April 2026.
- **current_value**: 28 days paid annual leave (including bank holidays if employer chooses)
- **source_url**: https://www.lewissilkin.com/insights/2026/03/19/employment-law-changes-in-april-2026
- **source_name**: Lewis Silkin — Employment Law Changes April 2026
- **requires_written_policy**: false

### meal_breaks

*UK Working Time Regulations 1998: workers are entitled to a 20-minute uninterrupted rest break if working more than 6 hours. This is a minimum — no specific meal break duration required beyond the 20-minute rest break.*

### final_pay

*No statutory final pay timing rules in the UK beyond contractual obligations. Pay must be made on the normal pay date.*

### pay_frequency

*No statutory pay frequency requirements in the UK. Pay frequency is contractual. Employers must provide itemised pay statements.*

### scheduling_reporting

*No predictive scheduling or reporting time pay requirements in the UK.*

### workers_comp

*Employers' Liability (Compulsory Insurance) Act 1969 requires employers to have at least £5 million employers' liability insurance. RIDDOR (Reporting of Injuries, Diseases and Dangerous Occurrences Regulations 2013) requires reporting of specified workplace injuries, diseases, and dangerous occurrences to HSE.*

### workplace_safety

*Health and Safety at Work Act 1974 is the primary workplace safety legislation. HSE enforces. Employers with 5+ employees must have a written health and safety policy. Risk assessments required for all workplaces. Manufacturing-specific requirements covered under PUWER, LOLER, COSHH, and Noise Regulations above.*

### anti_discrimination

*Equality Act 2010 protects against discrimination based on 9 protected characteristics: age, disability, gender reassignment, marriage/civil partnership, pregnancy/maternity, race, religion/belief, sex, sexual orientation. No mandatory harassment prevention training, but Employment Rights Act 2025 strengthens protections.*

### minor_work_permit

*Children and Young Persons Act 1933 (as amended). Local authority bylaws regulate employment of children under school-leaving age. Work permits required from local education authority. Restrictions on hours and types of work for under-18s.*
