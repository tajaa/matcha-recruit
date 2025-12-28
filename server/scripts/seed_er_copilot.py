#!/usr/bin/env python3
"""Seed script for ER Copilot test data.

Creates 6 investigation cases with realistic documents, evidence chunks, and analysis results.

Usage:
    cd server
    python scripts/seed_er_copilot.py
"""

import asyncio
import json
import os
import secrets
import sys
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha_recruit")


def generate_case_number() -> str:
    """Generate a unique case number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"ER-{now.year}-{now.month:02d}-{random_suffix}"


# =============================================================================
# Sample Document Content
# =============================================================================

DOCUMENTS = {
    "harassment": {
        "transcript_complainant": """INTERVIEW TRANSCRIPT
Case: Workplace Harassment Investigation
Date: December 15, 2024
Interviewer: Sarah Chen, HR Manager
Interviewee: Michael Torres, Software Engineer (Complainant)

---

[10:05 AM]
CHEN: Thank you for meeting with me today, Michael. I want to assure you that everything discussed here is confidential. Can you describe what happened on December 10th?

TORRES: Yes. I was in the break room around 2 PM getting coffee when David Kim came in. He started making comments about my accent, saying things like "speak English properly" and mocking the way I pronounced certain words.

[10:08 AM]
CHEN: Had this happened before?

TORRES: Yes, it's been going on for about two months now. At first it was subtle - little jokes here and there. But it's gotten worse. On December 5th, he sent me an email with a "funny" video mocking Hispanic accents. I still have that email.

[10:12 AM]
CHEN: Did anyone else witness the December 10th incident?

TORRES: Yes, Jennifer Walsh was in the break room too. She looked uncomfortable but didn't say anything. I think she was afraid to get involved.

[10:15 AM]
CHEN: How has this affected your work?

TORRES: I've been avoiding team meetings. I eat lunch at my desk now. My productivity has dropped because I'm constantly anxious. I've even thought about quitting, but I've been here for three years and I really liked this job before all this started.

[10:20 AM]
CHEN: Have you reported this to anyone before today?

TORRES: I mentioned it to my manager, Lisa Park, about a month ago. She said she'd talk to David, but nothing changed. If anything, it got worse after that.

[10:25 AM]
CHEN: Is there anything else you'd like to add?

TORRES: I just want it to stop. I don't want anyone fired necessarily, but this can't continue. I deserve to work in a place where I'm respected.

--- END OF TRANSCRIPT ---""",

        "transcript_accused": """INTERVIEW TRANSCRIPT
Case: Workplace Harassment Investigation
Date: December 16, 2024
Interviewer: Sarah Chen, HR Manager
Interviewee: David Kim, Senior Developer (Respondent)

---

[2:00 PM]
CHEN: David, thank you for coming in. I need to discuss some concerns that have been raised about workplace interactions.

KIM: Sure, what's this about?

[2:02 PM]
CHEN: There have been reports of comments made about a colleague's accent and cultural background. Can you tell me about your interactions with Michael Torres?

KIM: Michael? We work together on the backend team. I mean, we joke around sometimes, but it's all in good fun. Everyone jokes around.

[2:05 PM]
CHEN: Can you describe what kind of jokes?

KIM: Just, you know, playful stuff. Sometimes I'll tease him about his pronunciation. But he laughs too. I'm not trying to be mean or anything.

[2:08 PM]
CHEN: Did you send Michael an email with a video on December 5th?

KIM: Oh, that? It was just a comedy video I found funny. I share stuff like that with lots of people. I didn't think it was offensive.

[2:12 PM]
CHEN: What about the incident in the break room on December 10th?

KIM: I honestly don't remember anything specific. I probably said something joking around. But I never meant to hurt anyone's feelings. If Michael was offended, I wish he had just told me directly.

[2:15 PM]
CHEN: Were you aware that Michael had spoken to Lisa Park about your comments?

KIM: Lisa mentioned something to me about being more careful, but she didn't make it seem serious. I thought it was just HR being overly cautious.

[2:18 PM]
CHEN: Is there anything you'd like to add?

KIM: Look, I've worked here for five years. I'm not a racist or a bully. If I offended Michael, I'm sorry, but I think this is being blown out of proportion.

--- END OF TRANSCRIPT ---""",

        "transcript_witness": """INTERVIEW TRANSCRIPT
Case: Workplace Harassment Investigation
Date: December 16, 2024
Interviewer: Sarah Chen, HR Manager
Interviewee: Jennifer Walsh, Product Designer (Witness)

---

[3:30 PM]
CHEN: Jennifer, thank you for speaking with me. I understand you may have witnessed an incident in the break room on December 10th?

WALSH: Yes, I was there getting tea when David and Michael came in.

[3:32 PM]
CHEN: Can you describe what you observed?

WALSH: David was talking to Michael about some code review, and then he started imitating Michael's accent. He was saying things in an exaggerated accent, like "Oh, let me feex the bug." It was clearly mocking Michael.

[3:35 PM]
CHEN: How did Michael react?

WALSH: He kind of laughed nervously at first, but you could tell he was uncomfortable. His face got red and he left pretty quickly after that.

[3:38 PM]
CHEN: Have you witnessed similar incidents before?

WALSH: Yeah, unfortunately. I've seen David make comments in team meetings too. Little digs about Michael's English or asking him to "repeat that in American." People usually just go quiet when it happens.

[3:42 PM]
CHEN: Why didn't you report this earlier?

WALSH: Honestly? David's been here a long time and he's close with some of the managers. I didn't want to cause trouble for myself. But I feel terrible about not saying anything. Michael doesn't deserve to be treated that way.

[3:45 PM]
CHEN: Is there anything else you'd like to add?

WALSH: Just that this isn't the first time David has made people uncomfortable. He makes "jokes" about different things - people's appearances, backgrounds. Most people just avoid him.

--- END OF TRANSCRIPT ---""",

        "email_evidence": """From: David Kim <david.kim@acmecorp.com>
To: Michael Torres <michael.torres@acmecorp.com>
Date: December 5, 2024 11:42 AM
Subject: LOL you have to see this

Hey man,

Found this video and thought of you haha. No offense!

[VIDEO LINK: "Funny Accent Compilation"]

Let me know what you think!

-David

---

From: Michael Torres <michael.torres@acmecorp.com>
To: David Kim <david.kim@acmecorp.com>
Date: December 5, 2024 2:15 PM
Subject: RE: LOL you have to see this

David,

I don't find this funny. Please don't send me stuff like this.

Michael

---

From: David Kim <david.kim@acmecorp.com>
To: Michael Torres <michael.torres@acmecorp.com>
Date: December 5, 2024 2:22 PM
Subject: RE: LOL you have to see this

Chill out dude, it's just a joke. Don't be so sensitive.

-D""",

        "email_complaint": """From: Michael Torres <michael.torres@acmecorp.com>
To: Lisa Park <lisa.park@acmecorp.com>
Date: November 15, 2024 4:30 PM
Subject: Concerns about David Kim's behavior

Hi Lisa,

I wanted to bring something to your attention. Over the past few weeks, David Kim has been making repeated comments about my accent and background that I find offensive. He often imitates my speech in front of others and makes jokes at my expense.

I've tried to ignore it, hoping it would stop, but it's getting worse. Last week in the sprint planning meeting, he asked me to "translate" what I said even though everyone else clearly understood me.

I'm not sure how to handle this and would appreciate your guidance.

Thanks,
Michael""",

        "email_manager_response": """From: Lisa Park <lisa.park@acmecorp.com>
To: Michael Torres <michael.torres@acmecorp.com>
Date: November 16, 2024 9:15 AM
Subject: RE: Concerns about David Kim's behavior

Michael,

Thank you for bringing this to my attention. I'm sorry to hear you've been experiencing this.

I'll have a conversation with David about appropriate workplace behavior. Please let me know if anything else happens.

Best,
Lisa"""
    },

    "expense_fraud": {
        "policy_doc": """ACME CORPORATION EXPENSE POLICY
Version 3.2 | Effective Date: January 1, 2024

1. PURPOSE
This policy establishes guidelines for business expense reimbursement to ensure proper use of company funds.

2. SCOPE
This policy applies to all employees authorized to incur business expenses on behalf of the company.

3. GENERAL GUIDELINES
3.1 All expenses must be legitimate business expenses incurred while performing job duties.
3.2 Expenses must be reasonable and necessary.
3.3 Original receipts are required for all expenses over $25.
3.4 Expenses must be submitted within 30 days of being incurred.

4. MEAL EXPENSES
4.1 Daily meal limits:
    - Breakfast: $20
    - Lunch: $30
    - Dinner: $50
4.2 Alcohol is not reimbursable.
4.3 Meals with clients require prior manager approval and documentation of business purpose.

5. TRAVEL EXPENSES
5.1 Air travel must be booked at least 14 days in advance when possible.
5.2 Economy class is required for flights under 4 hours.
5.3 Hotel accommodations should not exceed $200/night without prior approval.
5.4 Personal travel combined with business travel must be clearly documented.

6. PROHIBITED EXPENSES
The following are NOT reimbursable:
- Personal expenses of any kind
- Entertainment without documented business purpose
- Gifts over $50 per person
- Traffic violations or parking tickets
- Expenses for family members

7. APPROVAL REQUIREMENTS
7.1 Expenses under $500: Direct manager approval
7.2 Expenses $500-$2000: Director approval
7.3 Expenses over $2000: VP approval

8. FRAUD AND MISUSE
Submitting false or inflated expense claims is grounds for immediate termination and may result in legal action. Employees must certify that all submitted expenses are accurate and comply with this policy.

9. REPORTING VIOLATIONS
Suspected policy violations should be reported to HR or the Ethics Hotline at ethics@acmecorp.com.""",

        "transcript_accused": """INTERVIEW TRANSCRIPT
Case: Expense Fraud Investigation
Date: December 18, 2024
Interviewer: Robert Martinez, Finance Director
Interviewee: James Wilson, Regional Sales Manager (Subject)

---

[10:00 AM]
MARTINEZ: James, we've been reviewing expense reports and found some irregularities we need to discuss.

WILSON: Okay, what kind of irregularities?

[10:02 AM]
MARTINEZ: In October, you submitted receipts for three client dinners totaling $2,400. But when we contacted the restaurants, they had no record of reservations under your name or the company name on those dates.

WILSON: That's strange. Maybe they lost the records? Those were legitimate dinners.

[10:05 AM]
MARTINEZ: We also found that several of your hotel receipts appear to have been altered. The original amounts were changed.

WILSON: I... I don't know what you're talking about.

[10:08 AM]
MARTINEZ: James, we have the original receipts from the hotels. One stay was $145, but your submission shows $245. Another was $167, submitted as $267.

WILSON: [Long pause] Look, I've been under a lot of financial pressure lately. My wife lost her job, we have medical bills...

[10:12 AM]
MARTINEZ: Are you saying you intentionally falsified these expense reports?

WILSON: I'm not proud of it. But I rationalized it - I work so hard, travel constantly, miss time with my family. I thought... I thought the company could afford it.

[10:15 AM]
MARTINEZ: How long has this been going on?

WILSON: About six months. Maybe $8,000 to $10,000 total. I know I messed up. I'll pay it all back.

[10:18 AM]
MARTINEZ: I appreciate your honesty now, but this is a serious matter. We'll need to continue this investigation and involve HR.

--- END OF TRANSCRIPT ---""",

        "transcript_manager": """INTERVIEW TRANSCRIPT
Case: Expense Fraud Investigation
Date: December 18, 2024
Interviewer: Robert Martinez, Finance Director
Interviewee: Patricia Evans, VP of Sales

---

[2:00 PM]
MARTINEZ: Patricia, as James Wilson's supervisor, I need to ask you some questions about his expense reports.

EVANS: Of course. I heard there's an investigation.

[2:02 PM]
MARTINEZ: You've been approving James's expense reports. Did you notice anything unusual?

EVANS: Honestly, he's one of our top performers, so I trusted his submissions. I probably didn't scrutinize them as closely as I should have.

[2:05 PM]
MARTINEZ: His Q4 expenses were 40% higher than other regional managers. Did that raise any flags?

EVANS: I noticed they were higher, but James has the largest territory and more client visits. I assumed it was justified.

[2:08 PM]
MARTINEZ: Did you ever verify the business purpose of his client meals?

EVANS: No. I should have requested more documentation. Looking back, some of the dinner amounts did seem high, but I didn't question them.

[2:12 PM]
MARTINEZ: Were there any complaints from James about the expense process or limits?

EVANS: He mentioned a few times that the hotel limits were unrealistic for major cities. But lots of sales people say that.

[2:15 PM]
MARTINEZ: Is there anything else relevant?

EVANS: Just that I feel responsible. I should have been more diligent in my oversight.

--- END OF TRANSCRIPT ---""",

        "expense_report": """EXPENSE REPORT SUMMARY - JAMES WILSON
October 2024

Date        | Description                  | Category    | Amount   | Status
------------|------------------------------|-------------|----------|--------
10/03/2024  | Client dinner - TechStart    | Meals       | $847.00  | FLAGGED
10/08/2024  | Marriott Dallas - 2 nights   | Lodging     | $494.00  | FLAGGED
10/12/2024  | Client dinner - Innovate Inc | Meals       | $723.00  | FLAGGED
10/15/2024  | Hilton Chicago - 3 nights    | Lodging     | $801.00  | FLAGGED
10/22/2024  | Client dinner - DataFlow     | Meals       | $834.00  | FLAGGED
10/25/2024  | Flight to NYC                | Travel      | $425.00  | APPROVED
10/28/2024  | Hotel NYC - 2 nights         | Lodging     | $534.00  | FLAGGED

TOTAL FLAGGED: $4,233.00
TOTAL APPROVED: $425.00
TOTAL SUBMITTED: $4,658.00

AUDITOR NOTES:
- Restaurant receipts for 10/03, 10/12, 10/22 could not be verified
- Hotel amounts exceed limits without required pre-approval
- Pattern of round-number alterations (+$100) on lodging receipts
- No client names or business purpose documented for meals"""
    },

    "discrimination": {
        "transcript_complainant": """INTERVIEW TRANSCRIPT
Case: Hiring Discrimination Investigation
Date: December 19, 2024
Interviewer: Angela Foster, HR Director
Interviewee: Dr. Maria Santos, Senior Researcher (Internal Candidate)

---

[9:00 AM]
FOSTER: Dr. Santos, thank you for bringing this matter forward. Can you explain your concerns about the Research Director hiring process?

SANTOS: Yes. I applied for the Research Director position in October. I've been with the company for eight years, have a PhD, and have led three major projects. I was told I didn't get the position because I "wasn't the right cultural fit."

[9:03 AM]
FOSTER: What do you believe that meant?

SANTOS: The person they hired - Brian Thompson - has five years of experience, a master's degree, and has never led a major project here. The only significant difference between us is that I'm a 52-year-old woman, and he's a 35-year-old man.

[9:06 AM]
FOSTER: Were you given any other feedback?

SANTOS: The VP, Richard Hayes, told me I should "focus on the technical work I do so well" rather than management. But my performance reviews for the past three years all specifically praise my leadership abilities.

[9:10 AM]
FOSTER: Did anyone explicitly mention your age or gender?

SANTOS: Not directly. But during my interview, Richard asked if I'd have the "energy" to manage a larger team and whether my family responsibilities might conflict with the travel requirements. He didn't ask Brian those questions - I checked with him.

[9:14 AM]
FOSTER: How do you know what Brian was asked?

SANTOS: Brian and I are friends. He was surprised he got the job over me and felt bad about it. He told me his interview was mostly about his ideas for the department.

[9:17 AM]
FOSTER: Is there anything else relevant?

SANTOS: In the past two years, our department has promoted six people to senior roles. All six were men under 45. Four women applied for various positions and were all passed over. That seems like more than coincidence.

--- END OF TRANSCRIPT ---""",

        "transcript_hiring_manager": """INTERVIEW TRANSCRIPT
Case: Hiring Discrimination Investigation
Date: December 20, 2024
Interviewer: Angela Foster, HR Director
Interviewee: Richard Hayes, VP of Research

---

[11:00 AM]
FOSTER: Richard, I need to discuss the Research Director hiring process with you. There's been a complaint.

HAYES: I assume this is about Maria Santos. Look, she's a brilliant researcher, but she wasn't right for this particular role.

[11:03 AM]
FOSTER: Can you explain what qualifications Brian Thompson had that Dr. Santos lacked?

HAYES: It's not just about qualifications on paper. Brian has a vision for modernizing the department. He's energetic, brings fresh ideas, and can connect with the younger researchers.

[11:06 AM]
FOSTER: Dr. Santos has more experience and education. How did you weigh those factors?

HAYES: Experience isn't everything. Sometimes you need new perspectives. Maria is great at what she does, but she's more of a specialist than a leader.

[11:10 AM]
FOSTER: Her performance reviews consistently highlight her leadership abilities.

HAYES: Those reviews are about leading projects, not managing people long-term. It's different.

[11:13 AM]
FOSTER: In the interview, did you ask Dr. Santos about her energy levels or family responsibilities?

HAYES: I may have asked about her bandwidth for the role. That's a legitimate question. The job requires a lot of travel.

[11:16 AM]
FOSTER: Did you ask Brian Thompson the same questions?

HAYES: I don't remember exactly what I asked everyone. I conduct dozens of interviews.

[11:19 AM]
FOSTER: Are you aware that no women have been promoted to senior roles in your department in the past two years?

HAYES: That's just how the candidate pools worked out. We hire the best person for each job regardless of gender or age. If you're suggesting I'm biased, that's offensive.

--- END OF TRANSCRIPT ---""",

        "transcript_witness": """INTERVIEW TRANSCRIPT
Case: Hiring Discrimination Investigation
Date: December 20, 2024
Interviewer: Angela Foster, HR Director
Interviewee: Brian Thompson, Research Director (Recently Hired)

---

[2:30 PM]
FOSTER: Brian, I appreciate you speaking with me about the hiring process for your current role.

THOMPSON: Of course. Maria mentioned she filed a complaint. I want to be helpful.

[2:32 PM]
FOSTER: Can you describe your interview process?

THOMPSON: I had three interviews - with Richard, the panel, and the CEO. They asked about my research vision, how I'd structure the team, thoughts on emerging technologies. Pretty standard.

[2:35 PM]
FOSTER: Were you asked about your energy levels, personal life, or family obligations?

THOMPSON: No, nothing like that. Why?

[2:37 PM]
FOSTER: I'm just gathering information. How would you compare your qualifications to Dr. Santos's?

THOMPSON: Honestly? She's more qualified on paper. When I got the offer, I was surprised. Maria has been here longer, has a PhD, and everyone respects her work. I assumed she'd get the job.

[2:40 PM]
FOSTER: Did Richard or anyone else explain why you were selected over her?

THOMPSON: Richard said I had "fresh energy" and would "shake things up." He mentioned wanting to "modernize" the department with "new blood."

[2:43 PM]
FOSTER: How do you interpret those comments now?

THOMPSON: Looking back... it sounds like code for wanting someone younger. That bothers me. Maria deserves to be evaluated fairly.

[2:46 PM]
FOSTER: Is there anything else you'd like to add?

THOMPSON: I want to do the right thing here. If there was discrimination, it should be addressed. Maria is a colleague and a friend.

--- END OF TRANSCRIPT ---""",

        "job_posting": """POSITION: Research Director
DEPARTMENT: R&D
REPORTS TO: VP of Research
LOCATION: Corporate Headquarters

ABOUT THE ROLE:
We're seeking a dynamic leader to drive our research initiatives into the future. The ideal candidate will bring fresh perspectives and energy to transform our research department.

RESPONSIBILITIES:
- Lead a team of 20+ researchers
- Develop and execute research strategy
- Manage $5M annual budget
- Travel 30% domestically and internationally
- Report to executive leadership

REQUIREMENTS:
- Advanced degree in relevant field (PhD preferred)
- 5+ years of research experience
- Proven leadership and team management
- Strong communication skills
- Ability to work in fast-paced environment

PREFERRED:
- Experience with modern research methodologies
- Track record of innovation
- Ability to mentor emerging talent

We are an equal opportunity employer and value diversity."""
    },

    "retaliation": {
        "transcript_complainant": """INTERVIEW TRANSCRIPT
Case: Retaliation Investigation
Date: December 21, 2024
Interviewer: Thomas Anderson, Senior HR Business Partner
Interviewee: Rachel Green, Marketing Coordinator (Complainant)

---

[10:00 AM]
ANDERSON: Rachel, you've filed a complaint alleging retaliation. Can you explain what happened?

GREEN: In September, I reported my manager, Mark Stevens, to HR for making inappropriate comments about my appearance. Two weeks after that investigation started, suddenly my performance is a problem.

[10:03 AM]
ANDERSON: What kind of performance issues were raised?

GREEN: Mark put me on a Performance Improvement Plan, claiming I missed deadlines and had attitude problems. But I have emails showing I met every deadline. The "attitude problem" started right after I filed my complaint.

[10:07 AM]
ANDERSON: Can you give specific examples of how things changed after your complaint?

GREEN: Before September, I got positive feedback. Mark even said I was "on track for promotion." After my complaint, he stopped including me in meetings, gave my projects to others, and criticized everything I did.

[10:11 AM]
ANDERSON: What about the inappropriate comments you originally reported?

GREEN: Mark would comment on my outfits, say things like "you look hot today" or "that dress is distracting." When I asked him to stop, he said I should "take a compliment." That's when I went to HR.

[10:15 AM]
ANDERSON: Were there witnesses to the original comments?

GREEN: My colleague Amy Chen heard some of them. She was uncomfortable but didn't want to get involved.

[10:18 AM]
ANDERSON: What outcome are you hoping for?

GREEN: I want the PIP removed from my record, and I don't want to report to Mark anymore. I shouldn't be punished for reporting harassment.

--- END OF TRANSCRIPT ---""",

        "transcript_manager": """INTERVIEW TRANSCRIPT
Case: Retaliation Investigation
Date: December 21, 2024
Interviewer: Thomas Anderson, Senior HR Business Partner
Interviewee: Mark Stevens, Marketing Manager (Respondent)

---

[2:00 PM]
ANDERSON: Mark, Rachel Green has alleged that you retaliated against her after she filed a complaint. What's your response?

STEVENS: That's completely false. Her performance issues are well-documented and have nothing to do with her complaint.

[2:03 PM]
ANDERSON: The timing is concerning - the PIP came two weeks after her complaint.

STEVENS: Coincidence. I had been documenting issues for months. I finally had enough evidence to move forward with the PIP.

[2:06 PM]
ANDERSON: Do you have documentation from before September?

STEVENS: I have notes. I'll need to gather them.

[2:08 PM]
ANDERSON: Her previous performance reviews were positive. What changed?

STEVENS: I was probably too lenient before. After HR talked to me about managing more effectively - completely separate from Rachel's complaint - I started holding everyone to higher standards.

[2:12 PM]
ANDERSON: Regarding the original complaint, did you make comments about Rachel's appearance?

STEVENS: I may have complimented her occasionally. Is that wrong now? You can't even be nice to people anymore without it being harassment.

[2:15 PM]
ANDERSON: She says you called her appearance "distracting."

STEVENS: If I said that, it was poor word choice. I was just being friendly. I certainly wasn't harassing her.

[2:18 PM]
ANDERSON: Is there anything else you'd like to add?

STEVENS: Rachel is trying to use the harassment claim as a shield to avoid accountability for her performance.

--- END OF TRANSCRIPT ---""",

        "email_performance_review": """From: Mark Stevens <mark.stevens@acmecorp.com>
To: Rachel Green <rachel.green@acmecorp.com>
CC: HR Department <hr@acmecorp.com>
Date: October 15, 2024
Subject: Performance Improvement Plan

Rachel,

Following our discussion, this email confirms the Performance Improvement Plan (PIP) that will be in effect for the next 60 days.

Areas of Concern:
1. Missed deadline on Q3 social media campaign (needs improvement)
2. Attitude issues in team meetings (needs improvement)
3. Quality of work below expectations (needs improvement)

Required Actions:
- Submit daily progress reports
- Attend weekly check-ins with me
- Complete all assignments 48 hours before deadline
- Maintain professional demeanor

Failure to meet these requirements may result in further disciplinary action up to and including termination.

Please sign and return this document.

Mark Stevens
Marketing Manager

---

From: Rachel Green <rachel.green@acmecorp.com>
To: Mark Stevens <mark.stevens@acmecorp.com>
CC: HR Department <hr@acmecorp.com>
Date: October 15, 2024
Subject: RE: Performance Improvement Plan

Mark,

I am signing this under protest. I have documentation showing all my deadlines were met. The Q3 social media campaign launched on September 15 as scheduled, which I can prove with emails and project management records.

I believe this PIP is retaliation for my complaint to HR last month.

Rachel Green"""
    },

    "safety": {
        "policy_doc": """ACME CORPORATION WORKPLACE SAFETY POLICY
Document No: SAF-001 | Version 2.5 | Effective: January 1, 2024

1. PURPOSE
To establish safety standards that protect employees, contractors, and visitors from workplace hazards.

2. SCOPE
This policy applies to all company facilities, operations, and personnel.

3. GENERAL REQUIREMENTS
3.1 All employees must complete safety training within 30 days of hire.
3.2 Personal Protective Equipment (PPE) must be worn in designated areas.
3.3 All accidents and near-misses must be reported within 24 hours.
3.4 Safety equipment must be inspected monthly.

4. WAREHOUSE AND MANUFACTURING AREAS
4.1 Forklift operation requires certification and annual recertification.
4.2 Maximum load limits must be observed at all times.
4.3 Emergency exits must remain clear and unobstructed.
4.4 Spills must be cleaned immediately and reported.

5. CHEMICAL HANDLING
5.1 MSDS sheets must be accessible for all chemicals.
5.2 Proper storage procedures must be followed.
5.3 PPE requirements vary by chemical classification.

6. REPORTING HAZARDS
6.1 Employees must report unsafe conditions immediately to supervisors.
6.2 No employee shall be disciplined for good-faith safety reports.
6.3 Serious hazards require immediate work stoppage.

7. MANAGEMENT RESPONSIBILITIES
7.1 Managers must ensure safety training compliance.
7.2 Safety equipment must be provided at no cost to employees.
7.3 Safety audits must be conducted quarterly.

8. VIOLATIONS
Safety violations may result in:
- Verbal warning (first offense)
- Written warning (second offense)
- Suspension (third offense)
- Termination (severe or repeated violations)

9. EMERGENCY PROCEDURES
See separate Emergency Response Plan (ERP-001).""",

        "transcript_employee": """INTERVIEW TRANSCRIPT
Case: Workplace Safety Violation Investigation
Date: December 22, 2024
Interviewer: Karen White, Safety Director
Interviewee: Carlos Rodriguez, Warehouse Worker

---

[9:00 AM]
WHITE: Carlos, I understand you witnessed the incident on December 18th. Can you describe what happened?

RODRIGUEZ: I was working in Section C when I heard a crash. A shelving unit collapsed. Product went everywhere. Luckily nobody was directly underneath, but Tom Bradley got hit by some falling boxes.

[9:03 AM]
WHITE: Do you know why the shelf collapsed?

RODRIGUEZ: It was overloaded. Way overloaded. We've been putting too much on those shelves for months. I've complained about it multiple times.

[9:06 AM]
WHITE: Who did you complain to?

RODRIGUEZ: My supervisor, Pete Morgan. He said we didn't have space anywhere else and to just make it work. He knows those shelves have weight limits, but we've been ignoring them since the busy season started.

[9:10 AM]
WHITE: Is this documented anywhere?

RODRIGUEZ: I sent Pete emails. He usually just responded verbally, telling me to stop worrying. But I kept copies of my emails.

[9:13 AM]
WHITE: How is Tom doing?

RODRIGUEZ: He has a concussion and a broken arm. Could have been much worse. If someone had been standing right there when it collapsed...

[9:16 AM]
WHITE: Have there been other safety concerns in the warehouse?

RODRIGUEZ: The forklift has had brake problems for weeks. I reported that too. Nothing gets fixed until someone gets hurt.

--- END OF TRANSCRIPT ---""",

        "transcript_supervisor": """INTERVIEW TRANSCRIPT
Case: Workplace Safety Violation Investigation
Date: December 22, 2024
Interviewer: Karen White, Safety Director
Interviewee: Pete Morgan, Warehouse Supervisor

---

[11:00 AM]
WHITE: Pete, I need to understand what led to the December 18th incident.

MORGAN: It was an accident. Those things happen in warehouses.

[11:02 AM]
WHITE: Were you aware the shelving was overloaded?

MORGAN: Define overloaded. We were within reasonable limits.

[11:04 AM]
WHITE: The shelves are rated for 2,000 pounds per section. Our inspection found sections loaded with over 3,500 pounds.

MORGAN: During peak season, we have to maximize space. Everyone does it. We've never had a problem before.

[11:07 AM]
WHITE: Carlos Rodriguez says he sent you emails warning about this.

MORGAN: Carlos worries too much. He's been here six months and thinks he knows everything about warehouse safety.

[11:10 AM]
WHITE: Did you receive and read those emails?

MORGAN: I probably got them, but I get hundreds of emails. I can't address every minor concern.

[11:13 AM]
WHITE: This wasn't minor. An employee is in the hospital.

MORGAN: And I feel terrible about that. But we were under pressure to handle the holiday volume. I did what I had to do.

[11:16 AM]
WHITE: Did you raise the space constraints with your manager?

MORGAN: I mentioned we were tight on space. They said to figure it out. So I did.

--- END OF TRANSCRIPT ---""",

        "incident_report": """INCIDENT REPORT

Report Number: IR-2024-1218-001
Date of Incident: December 18, 2024
Time: 2:47 PM
Location: Warehouse Section C, Aisle 7

DESCRIPTION:
Heavy-duty shelving unit (Serial #SH-2019-447) collapsed without warning. Approximately 3,800 lbs of packaged goods fell from a height of 12 feet. Employee Tom Bradley (ID: 45892) was struck by falling boxes while working in the adjacent aisle.

INJURIES:
- Tom Bradley: Concussion (moderate), fractured right radius, multiple contusions
- Transported to Memorial Hospital via ambulance at 3:05 PM
- Status: Treated and released, out of work for estimated 6-8 weeks

PROPERTY DAMAGE:
- Shelving unit: Destroyed, $2,400 replacement cost
- Inventory damage: Approximately $15,000 in damaged goods
- Floor damage: Minor cracks in concrete, repair estimate pending

ROOT CAUSE ANALYSIS (Preliminary):
1. Shelving overloaded beyond rated capacity (175% of maximum)
2. Visual inspection shows bracket fatigue and deformation
3. Last safety inspection of Section C: August 2024
4. No documented weight checks since September 2024

WITNESSES:
- Carlos Rodriguez (statement attached)
- Maria Silva (statement pending)
- Security camera footage preserved

IMMEDIATE ACTIONS TAKEN:
1. Area cordoned off
2. Adjacent shelving units unloaded as precaution
3. Facility-wide shelving inspection ordered
4. Incident reported to OSHA per requirements

INVESTIGATOR: Karen White, Safety Director
Date: December 19, 2024"""
    },

    "conflict_interest": {
        "transcript_employee": """INTERVIEW TRANSCRIPT
Case: Conflict of Interest Investigation
Date: December 23, 2024
Interviewer: Linda Park, Chief Compliance Officer
Interviewee: Steven Chen, Procurement Manager

---

[10:00 AM]
PARK: Steven, we've received information suggesting a potential conflict of interest in your vendor selection decisions. Can you tell me about your relationship with TechSupply Inc?

CHEN: TechSupply is one of our approved vendors. I've worked with them for years.

[10:03 AM]
PARK: Are you aware that your brother-in-law, Kevin Wright, is the CEO of TechSupply?

CHEN: [Pause] Yes, that's true. But it hasn't influenced my decisions.

[10:05 AM]
PARK: Did you disclose this relationship as required by company policy?

CHEN: I may have overlooked that requirement. It didn't seem relevant since I evaluate all vendors objectively.

[10:08 AM]
PARK: In the past year, TechSupply's contracts with us have increased from $200,000 to $1.8 million. Can you explain that?

CHEN: They've been competitive on pricing. They've also improved their service quality.

[10:12 AM]
PARK: We've reviewed the bids. In three cases, TechSupply was actually 15-20% higher than competitors but still won the contracts.

CHEN: There are factors beyond price - reliability, relationship, support quality.

[10:15 AM]
PARK: Those factors weren't documented in your evaluation reports.

CHEN: I may not have written everything down.

[10:18 AM]
PARK: Are you receiving any personal benefit from this relationship?

CHEN: [Long pause] Kevin... Kevin mentioned there might be a consulting opportunity after I retire next year.

[10:22 AM]
PARK: A job offer from a vendor you're awarding contracts to?

CHEN: Nothing was formalized. We just discussed possibilities.

--- END OF TRANSCRIPT ---""",

        "transcript_whistleblower": """INTERVIEW TRANSCRIPT
Case: Conflict of Interest Investigation
Date: December 23, 2024
Interviewer: Linda Park, Chief Compliance Officer
Interviewee: Jennifer Martinez, Senior Buyer (Anonymous Whistleblower)

---

[2:00 PM]
PARK: Jennifer, thank you for coming forward. You filed an anonymous report about procurement irregularities. Can you share more details?

MARTINEZ: I've worked with Steven Chen for three years. Over the past year, I've noticed TechSupply winning bids they shouldn't win. The numbers don't add up.

[2:03 PM]
PARK: Can you be specific?

MARTINEZ: Last March, we needed server equipment. I evaluated bids and recommended DataTech - they were 18% cheaper with better specs. Steven overruled me and gave it to TechSupply. He said he had information about DataTech's reliability issues, but he never documented it.

[2:07 PM]
PARK: How did you discover the family connection?

MARTINEZ: I saw Kevin Wright at our holiday party last year. He and Steven were very friendly. I asked a colleague who he was. That's when I learned Kevin's wife is Steven's sister.

[2:10 PM]
PARK: Did you raise concerns at the time?

MARTINEZ: I mentioned to Steven that we should document why we chose TechSupply over cheaper options. He got defensive and said not to question his decisions. After that, he started excluding me from TechSupply negotiations.

[2:14 PM]
PARK: Why did you wait to report this?

MARTINEZ: I wasn't sure if I was right. But when I saw TechSupply win another inflated contract last month, I felt I had to say something.

--- END OF TRANSCRIPT ---""",

        "contract_summary": """TECHSUPPLY INC. - CONTRACT SUMMARY
Prepared by: Compliance Department
Date: December 23, 2024

VENDOR INFORMATION:
- Company: TechSupply Inc.
- CEO: Kevin Wright (Related party: Brother-in-law of Procurement Manager Steven Chen)
- Relationship disclosed: NO
- Approved vendor since: 2018

CONTRACT HISTORY:

Year 2023:
- Total contracts: $200,000
- Number of awards: 3
- Average bid variance from lowest: +2%

Year 2024:
- Total contracts: $1,800,000
- Number of awards: 11
- Average bid variance from lowest: +17%

FLAGGED CONTRACTS (2024):

1. Server Hardware (March 2024)
   - TechSupply bid: $145,000
   - Lowest bid (DataTech): $118,000
   - Award: TechSupply
   - Variance: +23%
   - Documentation: Insufficient

2. Network Equipment (June 2024)
   - TechSupply bid: $320,000
   - Lowest bid (NetPro): $265,000
   - Award: TechSupply
   - Variance: +21%
   - Documentation: Insufficient

3. Software Licenses (October 2024)
   - TechSupply bid: $89,000
   - Lowest bid (SoftSource): $76,000
   - Award: TechSupply
   - Variance: +17%
   - Documentation: Insufficient

ESTIMATED OVERPAYMENT: $285,000

COMPLIANCE CONCERNS:
1. Undisclosed related party relationship
2. Pattern of awards to higher bidder without documented justification
3. Potential future employment arrangement
4. Exclusion of other staff from vendor negotiations"""
    }
}


# =============================================================================
# Analysis Results Templates
# =============================================================================

def create_timeline_analysis(case_type: str) -> dict:
    """Create realistic timeline analysis for each case type."""
    timelines = {
        "harassment": {
            "events": [
                {
                    "date": "2024-10-15",
                    "time": "Unknown",
                    "description": "Pattern of mocking comments begins",
                    "participants": ["David Kim", "Michael Torres"],
                    "source_document": "transcript_complainant.txt",
                    "confidence": "medium",
                    "supporting_quotes": ["it's been going on for about two months now"]
                },
                {
                    "date": "2024-11-15",
                    "time": "16:30",
                    "description": "Michael Torres reports concerns to manager Lisa Park",
                    "participants": ["Michael Torres", "Lisa Park"],
                    "source_document": "email_complaint.txt",
                    "confidence": "high",
                    "supporting_quotes": ["I wanted to bring something to your attention"]
                },
                {
                    "date": "2024-12-05",
                    "time": "11:42",
                    "description": "David Kim sends offensive video via email",
                    "participants": ["David Kim", "Michael Torres"],
                    "source_document": "email_evidence.txt",
                    "confidence": "high",
                    "supporting_quotes": ["Found this video and thought of you"]
                },
                {
                    "date": "2024-12-10",
                    "time": "14:00",
                    "description": "Break room incident witnessed by Jennifer Walsh",
                    "participants": ["David Kim", "Michael Torres", "Jennifer Walsh"],
                    "source_document": "transcript_complainant.txt",
                    "confidence": "high",
                    "supporting_quotes": ["I was in the break room around 2 PM"]
                }
            ],
            "gaps_identified": [
                "Limited documentation of incidents between October 15 and November 15",
                "Manager's conversation with David Kim not documented"
            ],
            "timeline_summary": "Timeline spans October-December 2024 with escalating harassment pattern culminating in documented December 10th incident."
        },
        "expense_fraud": {
            "events": [
                {
                    "date": "2024-06-01",
                    "time": "Unknown",
                    "description": "Expense fraud begins according to subject's admission",
                    "participants": ["James Wilson"],
                    "source_document": "transcript_accused.txt",
                    "confidence": "high",
                    "supporting_quotes": ["About six months"]
                },
                {
                    "date": "2024-10-03",
                    "time": "Unknown",
                    "description": "Fraudulent client dinner expense submitted - $847",
                    "participants": ["James Wilson"],
                    "source_document": "expense_report.txt",
                    "confidence": "high",
                    "supporting_quotes": ["Restaurant receipts could not be verified"]
                },
                {
                    "date": "2024-10-08",
                    "time": "Unknown",
                    "description": "Altered hotel receipt submitted - inflated by $100",
                    "participants": ["James Wilson"],
                    "source_document": "transcript_accused.txt",
                    "confidence": "high",
                    "supporting_quotes": ["One stay was $145, but your submission shows $245"]
                },
                {
                    "date": "2024-12-18",
                    "time": "10:00",
                    "description": "Subject admits to falsifying expenses during interview",
                    "participants": ["James Wilson", "Robert Martinez"],
                    "source_document": "transcript_accused.txt",
                    "confidence": "high",
                    "supporting_quotes": ["I'm not proud of it"]
                }
            ],
            "gaps_identified": [
                "Exact start date of fraudulent activity uncertain",
                "Full scope of altered receipts still being investigated"
            ],
            "timeline_summary": "Six-month pattern of expense fraud totaling approximately $8,000-$10,000 through fabricated receipts and inflated hotel charges."
        },
        "discrimination": {
            "events": [
                {
                    "date": "2024-10-01",
                    "time": "Unknown",
                    "description": "Research Director position posted",
                    "participants": ["HR Department"],
                    "source_document": "job_posting.txt",
                    "confidence": "high",
                    "supporting_quotes": ["dynamic leader", "fresh perspectives"]
                },
                {
                    "date": "2024-10-15",
                    "time": "Unknown",
                    "description": "Dr. Santos interviews with potentially discriminatory questions",
                    "participants": ["Maria Santos", "Richard Hayes"],
                    "source_document": "transcript_complainant.txt",
                    "confidence": "high",
                    "supporting_quotes": ["asked if I'd have the 'energy'", "family responsibilities"]
                },
                {
                    "date": "2024-11-01",
                    "time": "Unknown",
                    "description": "Brian Thompson hired for Research Director position",
                    "participants": ["Brian Thompson", "Richard Hayes"],
                    "source_document": "transcript_witness.txt",
                    "confidence": "high",
                    "supporting_quotes": ["fresh energy", "new blood"]
                },
                {
                    "date": "2024-12-19",
                    "time": "09:00",
                    "description": "Dr. Santos files discrimination complaint",
                    "participants": ["Maria Santos", "Angela Foster"],
                    "source_document": "transcript_complainant.txt",
                    "confidence": "high",
                    "supporting_quotes": ["wasn't the right cultural fit"]
                }
            ],
            "gaps_identified": [
                "Interview questions for other candidates not fully documented",
                "Historical promotion decisions need further review"
            ],
            "timeline_summary": "Hiring decision potentially influenced by age and gender bias, with less qualified male candidate selected over senior female researcher."
        },
        "retaliation": {
            "events": [
                {
                    "date": "2024-09-01",
                    "time": "Unknown",
                    "description": "Rachel Green reports harassment by Mark Stevens to HR",
                    "participants": ["Rachel Green", "HR Department"],
                    "source_document": "transcript_complainant.txt",
                    "confidence": "high",
                    "supporting_quotes": ["I reported my manager"]
                },
                {
                    "date": "2024-09-15",
                    "time": "Unknown",
                    "description": "Performance issues first raised by Mark Stevens",
                    "participants": ["Mark Stevens", "Rachel Green"],
                    "source_document": "transcript_complainant.txt",
                    "confidence": "medium",
                    "supporting_quotes": ["Two weeks after that investigation started"]
                },
                {
                    "date": "2024-10-15",
                    "time": "Unknown",
                    "description": "Rachel Green placed on Performance Improvement Plan",
                    "participants": ["Mark Stevens", "Rachel Green"],
                    "source_document": "email_performance_review.txt",
                    "confidence": "high",
                    "supporting_quotes": ["this email confirms the Performance Improvement Plan"]
                }
            ],
            "gaps_identified": [
                "Documentation of performance issues prior to September not provided",
                "Witness statements regarding original harassment limited"
            ],
            "timeline_summary": "Clear temporal correlation between harassment complaint and performance management actions suggests potential retaliation."
        },
        "safety": {
            "events": [
                {
                    "date": "2024-08-01",
                    "time": "Unknown",
                    "description": "Last documented safety inspection of Section C",
                    "participants": ["Safety Department"],
                    "source_document": "incident_report.txt",
                    "confidence": "high",
                    "supporting_quotes": ["Last safety inspection of Section C: August 2024"]
                },
                {
                    "date": "2024-09-01",
                    "time": "Unknown",
                    "description": "Carlos Rodriguez begins reporting overloading concerns",
                    "participants": ["Carlos Rodriguez", "Pete Morgan"],
                    "source_document": "transcript_employee.txt",
                    "confidence": "high",
                    "supporting_quotes": ["I've complained about it multiple times"]
                },
                {
                    "date": "2024-12-18",
                    "time": "14:47",
                    "description": "Shelving unit collapse injures Tom Bradley",
                    "participants": ["Tom Bradley", "Carlos Rodriguez"],
                    "source_document": "incident_report.txt",
                    "confidence": "high",
                    "supporting_quotes": ["Heavy-duty shelving unit collapsed without warning"]
                }
            ],
            "gaps_identified": [
                "Exact dates of Rodriguez's email complaints not specified",
                "Forklift brake issue reporting timeline unclear"
            ],
            "timeline_summary": "Months of ignored safety warnings culminated in preventable accident causing employee injury."
        },
        "conflict_interest": {
            "events": [
                {
                    "date": "2024-01-01",
                    "time": "Unknown",
                    "description": "TechSupply contracts begin significant increase",
                    "participants": ["Steven Chen", "TechSupply Inc."],
                    "source_document": "contract_summary.txt",
                    "confidence": "high",
                    "supporting_quotes": ["contracts have increased from $200,000 to $1.8 million"]
                },
                {
                    "date": "2024-03-01",
                    "time": "Unknown",
                    "description": "Server hardware contract awarded to TechSupply despite higher bid",
                    "participants": ["Steven Chen", "Jennifer Martinez"],
                    "source_document": "transcript_whistleblower.txt",
                    "confidence": "high",
                    "supporting_quotes": ["TechSupply winning bids they shouldn't win"]
                },
                {
                    "date": "2024-12-01",
                    "time": "Unknown",
                    "description": "Anonymous complaint filed about procurement irregularities",
                    "participants": ["Jennifer Martinez"],
                    "source_document": "transcript_whistleblower.txt",
                    "confidence": "high",
                    "supporting_quotes": ["I felt I had to say something"]
                },
                {
                    "date": "2024-12-23",
                    "time": "10:00",
                    "description": "Steven Chen admits to undisclosed relationship and job discussions",
                    "participants": ["Steven Chen", "Linda Park"],
                    "source_document": "transcript_employee.txt",
                    "confidence": "high",
                    "supporting_quotes": ["Kevin mentioned there might be a consulting opportunity"]
                }
            ],
            "gaps_identified": [
                "Full timeline of relationship disclosure requirements not reviewed",
                "All TechSupply contracts need individual review"
            ],
            "timeline_summary": "Undisclosed family relationship with vendor CEO led to biased contract awards and potential personal financial benefit."
        }
    }
    return timelines.get(case_type, {"events": [], "gaps": [], "summary": "No timeline available"})


def create_discrepancy_analysis(case_type: str) -> dict:
    """Create realistic discrepancy analysis for each case type."""
    discrepancies = {
        "harassment": {
            "discrepancies": [
                {
                    "type": "Conflicting accounts",
                    "severity": "high",
                    "description": "Nature of comments",
                    "statement_1": {"speaker": "Michael Torres", "quote": "He started making comments about my accent, saying things like 'speak English properly'", "location": "Interview transcript", "source_document_id": ""},
                    "statement_2": {"speaker": "David Kim", "quote": "Just, you know, playful stuff. Sometimes I'll tease him about his pronunciation", "location": "Interview transcript", "source_document_id": ""},
                    "analysis": "David Kim minimizes the severity of comments that Michael Torres and witness Jennifer Walsh describe as mocking and offensive."
                },
                {
                    "type": "Interpretation difference",
                    "severity": "medium",
                    "description": "Michael's reaction",
                    "statement_1": {"speaker": "David Kim", "quote": "he laughs too. I'm not trying to be mean", "location": "Interview transcript", "source_document_id": ""},
                    "statement_2": {"speaker": "Jennifer Walsh", "quote": "He kind of laughed nervously at first, but you could tell he was uncomfortable", "location": "Interview transcript", "source_document_id": ""},
                    "analysis": "David interprets nervous laughter as genuine enjoyment; witness clarifies it was discomfort."
                }
            ],
            "credibility_notes": [
                {"witness": "Michael Torres", "assessment": "Credible", "reasoning": "Consistent account with documentary evidence (emails)."},
                {"witness": "David Kim", "assessment": "Mixed", "reasoning": "Minimizes behavior, claims ignorance despite direct email exchange showing awareness."},
                {"witness": "Jennifer Walsh", "assessment": "Credible", "reasoning": "Independent witness corroborating complainant's account. No apparent bias."}
            ],
            "summary": "Significant discrepancies exist between respondent's characterization of events as 'joking' and multiple accounts describing the conduct as harassment."
        },
        "expense_fraud": {
            "discrepancies": [
                {
                    "topic": "Knowledge of irregularities",
                    "statements": [
                        {"speaker": "James Wilson", "content": "Those were legitimate dinners", "source": "transcript_accused.txt"},
                        {"speaker": "James Wilson", "content": "I'm not proud of it... I rationalized it", "source": "transcript_accused.txt"}
                    ],
                    "analysis": "Subject initially denied wrongdoing but later admitted to intentional falsification.",
                    "severity": "high"
                },
                {
                    "topic": "Supervisor oversight",
                    "statements": [
                        {"speaker": "Patricia Evans", "content": "I probably didn't scrutinize them as closely as I should have", "source": "transcript_manager.txt"},
                        {"speaker": "James Wilson", "content": "I thought the company could afford it", "source": "transcript_accused.txt"}
                    ],
                    "analysis": "Lack of managerial oversight created environment enabling fraud.",
                    "severity": "medium"
                }
            ],
            "credibility_notes": [
                {"witness": "James Wilson", "assessment": "Admitted to fraud after initial denial. Confession is credible but demonstrates dishonesty."},
                {"witness": "Patricia Evans", "assessment": "Admits to oversight failures. No evidence of complicity."}
            ],
            "summary": "Subject's confession eliminates credibility questions but raises concerns about approval processes and management oversight."
        },
        "discrimination": {
            "discrepancies": [
                {
                    "topic": "Interview questions",
                    "statements": [
                        {"speaker": "Maria Santos", "content": "Richard asked if I'd have the 'energy' to manage a larger team and whether my family responsibilities might conflict", "source": "transcript_complainant.txt"},
                        {"speaker": "Richard Hayes", "content": "I may have asked about her bandwidth for the role. That's a legitimate question", "source": "transcript_hiring_manager.txt"}
                    ],
                    "analysis": "Hayes reframes potentially discriminatory questions as legitimate; Brian Thompson confirms he wasn't asked similar questions.",
                    "severity": "high"
                },
                {
                    "topic": "Selection criteria",
                    "statements": [
                        {"speaker": "Richard Hayes", "content": "Brian has a vision... He's energetic, brings fresh ideas", "source": "transcript_hiring_manager.txt"},
                        {"speaker": "Brian Thompson", "content": "Richard said I had 'fresh energy' and would 'shake things up'... 'new blood'", "source": "transcript_witness.txt"}
                    ],
                    "analysis": "Language used ('energy', 'fresh', 'new blood') may constitute code for age-based preferences.",
                    "severity": "high"
                }
            ],
            "credibility_notes": [
                {"witness": "Maria Santos", "assessment": "Documented qualifications and performance reviews support her account."},
                {"witness": "Richard Hayes", "assessment": "Defensive responses and inability to articulate objective selection criteria raise concerns."},
                {"witness": "Brian Thompson", "assessment": "Provides candid, potentially adverse information. Highly credible."}
            ],
            "summary": "Multiple indicators of age and gender bias in hiring decision, with respondent's stated justifications unsupported by documentation."
        },
        "retaliation": {
            "discrepancies": [
                {
                    "topic": "Timing of performance issues",
                    "statements": [
                        {"speaker": "Rachel Green", "content": "Two weeks after that investigation started, suddenly my performance is a problem", "source": "transcript_complainant.txt"},
                        {"speaker": "Mark Stevens", "content": "I had been documenting issues for months", "source": "transcript_manager.txt"}
                    ],
                    "analysis": "Mark claims pre-existing documentation but has not produced evidence predating the harassment complaint.",
                    "severity": "high"
                },
                {
                    "topic": "Nature of original comments",
                    "statements": [
                        {"speaker": "Rachel Green", "content": "Mark would comment on my outfits, say things like 'you look hot today'", "source": "transcript_complainant.txt"},
                        {"speaker": "Mark Stevens", "content": "I may have complimented her occasionally. Is that wrong now?", "source": "transcript_manager.txt"}
                    ],
                    "analysis": "Mark minimizes conduct as 'compliments' that Rachel experienced as harassment.",
                    "severity": "medium"
                }
            ],
            "credibility_notes": [
                {"witness": "Rachel Green", "assessment": "Has documentary evidence (emails showing deadlines met). Credible."},
                {"witness": "Mark Stevens", "assessment": "Claims documentation exists but hasn't provided it. Defensive about both allegations."}
            ],
            "summary": "Strong circumstantial evidence of retaliation given timing. Manager's claimed prior documentation not yet verified."
        },
        "safety": {
            "discrepancies": [
                {
                    "topic": "Awareness of overloading",
                    "statements": [
                        {"speaker": "Carlos Rodriguez", "content": "I've complained about it multiple times... I sent Pete emails", "source": "transcript_employee.txt"},
                        {"speaker": "Pete Morgan", "content": "I probably got them, but I get hundreds of emails. I can't address every minor concern", "source": "transcript_supervisor.txt"}
                    ],
                    "analysis": "Supervisor dismisses documented safety concerns as 'minor' despite significant weight exceedance.",
                    "severity": "high"
                },
                {
                    "topic": "Compliance with limits",
                    "statements": [
                        {"speaker": "Pete Morgan", "content": "We were within reasonable limits", "source": "transcript_supervisor.txt"},
                        {"speaker": "Incident Report", "content": "Shelving overloaded beyond rated capacity (175% of maximum)", "source": "incident_report.txt"}
                    ],
                    "analysis": "Direct contradiction between supervisor's claim and documented evidence of severe overloading.",
                    "severity": "high"
                }
            ],
            "credibility_notes": [
                {"witness": "Carlos Rodriguez", "assessment": "Has email documentation of warnings. No motive to fabricate."},
                {"witness": "Pete Morgan", "assessment": "Statements contradicted by physical evidence. Attempts to minimize responsibility."}
            ],
            "summary": "Clear evidence that supervisor was warned but ignored safety concerns, directly causing the incident."
        },
        "conflict_interest": {
            "discrepancies": [
                {
                    "topic": "Influence on decisions",
                    "statements": [
                        {"speaker": "Steven Chen", "content": "it hasn't influenced my decisions", "source": "transcript_employee.txt"},
                        {"speaker": "Contract Summary", "content": "TechSupply was actually 15-20% higher than competitors but still won the contracts", "source": "contract_summary.txt"}
                    ],
                    "analysis": "Pattern of awarding contracts to related party at higher prices contradicts claim of objectivity.",
                    "severity": "high"
                },
                {
                    "topic": "Disclosure",
                    "statements": [
                        {"speaker": "Steven Chen", "content": "I may have overlooked that requirement", "source": "transcript_employee.txt"},
                        {"speaker": "Company Policy", "content": "Related party relationships must be disclosed", "source": "policy reference"}
                    ],
                    "analysis": "Failure to disclose was not inadvertent given ongoing business relationship and job discussions.",
                    "severity": "high"
                }
            ],
            "credibility_notes": [
                {"witness": "Steven Chen", "assessment": "Minimizes conduct despite documentary evidence. Admission of job discussions damages credibility."},
                {"witness": "Jennifer Martinez", "assessment": "Corroborated by contract data. Raised concerns through proper channels."}
            ],
            "summary": "Overwhelming evidence of undisclosed conflict of interest affecting business decisions to company's financial detriment."
        }
    }
    return discrepancies.get(case_type, {"discrepancies": [], "credibility_notes": [], "summary": "No discrepancy analysis available"})


def create_policy_analysis(case_type: str) -> dict:
    """Create realistic policy check analysis for each case type."""
    analyses = {
        "harassment": {
            "violations": [
                {
                    "policy": "Anti-Harassment Policy Section 3.1",
                    "description": "Prohibition on harassment based on national origin",
                    "evidence": [
                        {"quote": "speak English properly", "source": "transcript_complainant.txt"},
                        {"quote": "mocking the way I pronounced certain words", "source": "transcript_complainant.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Repeated mocking of accent constitutes national origin harassment under company policy."
                },
                {
                    "policy": "Electronic Communications Policy Section 2.3",
                    "description": "Prohibition on offensive content in company email",
                    "evidence": [
                        {"quote": "email with a 'funny' video mocking Hispanic accents", "source": "transcript_complainant.txt"}
                    ],
                    "severity": "medium",
                    "analysis": "Sending ethnically offensive content via company email violates acceptable use policy."
                },
                {
                    "policy": "Supervisor Responsibilities Section 4.1",
                    "description": "Duty to address reported harassment",
                    "evidence": [
                        {"quote": "she said she'd talk to David, but nothing changed", "source": "transcript_complainant.txt"}
                    ],
                    "severity": "medium",
                    "analysis": "Manager Lisa Park failed to effectively address reported harassment."
                }
            ],
            "applicable_policies": [
                "Anti-Harassment Policy",
                "Electronic Communications Policy",
                "Code of Conduct",
                "Supervisor Responsibilities"
            ],
            "recommendations": [
                "Substantiate harassment finding against David Kim",
                "Consider corrective action ranging from written warning to termination",
                "Address Lisa Park's failure to escalate",
                "Require anti-harassment training for department"
            ]
        },
        "expense_fraud": {
            "violations": [
                {
                    "policy": "Expense Policy Section 8",
                    "description": "Fraud and misuse - grounds for termination",
                    "evidence": [
                        {"quote": "I'm not proud of it", "source": "transcript_accused.txt"},
                        {"quote": "Maybe $8,000 to $10,000 total", "source": "transcript_accused.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Admitted falsification of expense reports constitutes fraud under policy."
                },
                {
                    "policy": "Expense Policy Section 3.3",
                    "description": "Original receipts required for expenses over $25",
                    "evidence": [
                        {"quote": "Restaurant receipts could not be verified", "source": "expense_report.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Fabricated receipts violate documentation requirements."
                },
                {
                    "policy": "Expense Policy Section 7",
                    "description": "Approval requirements and manager oversight",
                    "evidence": [
                        {"quote": "I probably didn't scrutinize them as closely as I should have", "source": "transcript_manager.txt"}
                    ],
                    "severity": "medium",
                    "analysis": "Approval process failed to detect obvious irregularities."
                }
            ],
            "applicable_policies": [
                "Expense Policy",
                "Code of Business Conduct",
                "Financial Controls Policy"
            ],
            "recommendations": [
                "Termination for cause - James Wilson",
                "Recovery of fraudulent amounts",
                "Consider referral for potential legal action",
                "Strengthen expense approval process",
                "Coaching for Patricia Evans on approval responsibilities"
            ]
        },
        "discrimination": {
            "violations": [
                {
                    "policy": "Equal Employment Opportunity Policy",
                    "description": "Prohibition on age and gender discrimination in hiring",
                    "evidence": [
                        {"quote": "asked if I'd have the 'energy'", "source": "transcript_complainant.txt"},
                        {"quote": "fresh energy", "source": "transcript_witness.txt"},
                        {"quote": "new blood", "source": "transcript_witness.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Interview questions and selection language suggest age-based decision making."
                },
                {
                    "policy": "Interview Guidelines Section 2",
                    "description": "Prohibited interview questions",
                    "evidence": [
                        {"quote": "whether my family responsibilities might conflict with the travel requirements", "source": "transcript_complainant.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Questions about family responsibilities are prohibited as potentially discriminatory."
                },
                {
                    "policy": "Hiring Documentation Requirements",
                    "description": "Selection decisions must be documented with objective criteria",
                    "evidence": [
                        {"quote": "It's not just about qualifications on paper", "source": "transcript_hiring_manager.txt"}
                    ],
                    "severity": "medium",
                    "analysis": "Failure to document objective reasons for selecting less qualified candidate."
                }
            ],
            "applicable_policies": [
                "Equal Employment Opportunity Policy",
                "Interview Guidelines",
                "Hiring Documentation Requirements",
                "Anti-Discrimination Policy"
            ],
            "recommendations": [
                "Find discrimination claim substantiated",
                "Review Research Director hiring decision",
                "Consider remedial action for Dr. Santos",
                "Require EEO training for Richard Hayes",
                "Audit department promotion history"
            ]
        },
        "retaliation": {
            "violations": [
                {
                    "policy": "Anti-Retaliation Policy Section 1",
                    "description": "Prohibition on adverse action following good-faith complaint",
                    "evidence": [
                        {"quote": "Two weeks after that investigation started, suddenly my performance is a problem", "source": "transcript_complainant.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Timing of PIP strongly suggests retaliatory motive."
                },
                {
                    "policy": "Performance Management Policy Section 3",
                    "description": "PIPs require documented history of performance issues",
                    "evidence": [
                        {"quote": "I have emails showing I met every deadline", "source": "transcript_complainant.txt"},
                        {"quote": "I'll need to gather them", "source": "transcript_manager.txt"}
                    ],
                    "severity": "high",
                    "analysis": "PIP issued without documented prior performance issues."
                },
                {
                    "policy": "Anti-Harassment Policy",
                    "description": "Prohibition on unwelcome comments about appearance",
                    "evidence": [
                        {"quote": "you look hot today", "source": "transcript_complainant.txt"},
                        {"quote": "that dress is distracting", "source": "transcript_complainant.txt"}
                    ],
                    "severity": "medium",
                    "analysis": "Original harassment complaint appears substantiated."
                }
            ],
            "applicable_policies": [
                "Anti-Retaliation Policy",
                "Performance Management Policy",
                "Anti-Harassment Policy",
                "Code of Conduct"
            ],
            "recommendations": [
                "Find retaliation claim substantiated",
                "Remove PIP from Rachel Green's record",
                "Transfer Rachel Green to different supervisor",
                "Corrective action for Mark Stevens (both harassment and retaliation)",
                "Monitor for further retaliatory conduct"
            ]
        },
        "safety": {
            "violations": [
                {
                    "policy": "Safety Policy Section 4.1",
                    "description": "Maximum load limits must be observed",
                    "evidence": [
                        {"quote": "Shelving overloaded beyond rated capacity (175% of maximum)", "source": "incident_report.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Severe and knowing violation of weight limits directly caused incident."
                },
                {
                    "policy": "Safety Policy Section 6.1",
                    "description": "Employees must report unsafe conditions to supervisors",
                    "evidence": [
                        {"quote": "I've complained about it multiple times", "source": "transcript_employee.txt"}
                    ],
                    "severity": "low",
                    "analysis": "Carlos Rodriguez fulfilled reporting obligation; failure was in management response."
                },
                {
                    "policy": "Safety Policy Section 7.3",
                    "description": "Safety audits must be conducted quarterly",
                    "evidence": [
                        {"quote": "Last safety inspection of Section C: August 2024", "source": "incident_report.txt"}
                    ],
                    "severity": "medium",
                    "analysis": "Quarterly inspection schedule not maintained (4+ months since last inspection)."
                }
            ],
            "applicable_policies": [
                "Workplace Safety Policy",
                "Emergency Response Plan",
                "Warehouse Operations Manual",
                "Supervisor Safety Responsibilities"
            ],
            "recommendations": [
                "Serious disciplinary action for Pete Morgan",
                "Immediate facility-wide safety audit",
                "Review all shelving load compliance",
                "Update inspection schedule and enforcement",
                "OSHA compliance review"
            ]
        },
        "conflict_interest": {
            "violations": [
                {
                    "policy": "Conflict of Interest Policy Section 2",
                    "description": "Mandatory disclosure of related party relationships",
                    "evidence": [
                        {"quote": "I may have overlooked that requirement", "source": "transcript_employee.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Failed to disclose family relationship with vendor CEO."
                },
                {
                    "policy": "Procurement Policy Section 5",
                    "description": "Vendor selection must be based on objective criteria",
                    "evidence": [
                        {"quote": "TechSupply was actually 15-20% higher than competitors but still won", "source": "contract_summary.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Pattern of awarding contracts to higher bidder without documented justification."
                },
                {
                    "policy": "Code of Business Conduct Section 7",
                    "description": "Prohibition on personal benefit from vendor relationships",
                    "evidence": [
                        {"quote": "there might be a consulting opportunity after I retire", "source": "transcript_employee.txt"}
                    ],
                    "severity": "high",
                    "analysis": "Discussing future employment with vendor while making procurement decisions."
                }
            ],
            "applicable_policies": [
                "Conflict of Interest Policy",
                "Procurement Policy",
                "Code of Business Conduct",
                "Ethics Policy"
            ],
            "recommendations": [
                "Termination for cause - Steven Chen",
                "Void current TechSupply contracts and rebid",
                "Seek recovery of estimated $285,000 overpayment",
                "Consider legal action",
                "Strengthen procurement oversight",
                "Annual conflict of interest certification"
            ]
        }
    }
    return analyses.get(case_type, {"violations": [], "applicable_policies": [], "recommendations": []})


# =============================================================================
# Main Seed Function
# =============================================================================

async def seed_er_copilot():
    """Seed ER Copilot with test data."""
    print("Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Get or create admin user
        admin = await conn.fetchrow("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if not admin:
            print("ERROR: No admin user found. Please create one first.")
            return

        admin_id = str(admin["id"])
        print(f"Using admin user: {admin_id}")

        # Define test cases
        test_cases = [
            {
                "title": "Workplace Harassment - Torres v. Kim",
                "description": "Investigation into alleged harassment based on national origin. Complainant Michael Torres reports ongoing mocking of his accent by colleague David Kim.",
                "status": "open",
                "type": "harassment"
            },
            {
                "title": "Expense Fraud Investigation - James Wilson",
                "description": "Investigation into suspected falsification of expense reports by Regional Sales Manager James Wilson, including fabricated receipts and inflated charges.",
                "status": "in_review",
                "type": "expense_fraud"
            },
            {
                "title": "Hiring Discrimination - Dr. Santos Complaint",
                "description": "Age and gender discrimination complaint regarding Research Director hiring. Dr. Maria Santos alleges she was passed over for a less qualified male candidate.",
                "status": "pending_determination",
                "type": "discrimination"
            },
            {
                "title": "Retaliation Complaint - Rachel Green",
                "description": "Allegation that manager Mark Stevens placed complainant on PIP in retaliation for filing harassment complaint.",
                "status": "open",
                "type": "retaliation"
            },
            {
                "title": "Warehouse Safety Violation - Section C Collapse",
                "description": "Investigation into December 18th shelving collapse that injured employee Tom Bradley. Multiple prior warnings about overloading were allegedly ignored.",
                "status": "closed",
                "type": "safety"
            },
            {
                "title": "Conflict of Interest - Procurement Investigation",
                "description": "Investigation into undisclosed family relationship between Procurement Manager Steven Chen and TechSupply Inc. CEO, with potential contract award bias.",
                "status": "in_review",
                "type": "conflict_interest"
            }
        ]

        created_cases = []

        for case_data in test_cases:
            print(f"\nCreating case: {case_data['title']}")

            # Create case
            case_number = generate_case_number()
            case_row = await conn.fetchrow(
                """
                INSERT INTO er_cases (case_number, title, description, status, created_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, case_number
                """,
                case_number,
                case_data["title"],
                case_data["description"],
                case_data["status"],
                admin_id
            )
            case_id = str(case_row["id"])
            print(f"  Created case {case_row['case_number']}")

            # Log case creation
            await conn.execute(
                """
                INSERT INTO er_audit_log (case_id, user_id, action, entity_type, entity_id, details)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                case_id, admin_id, "case_created", "case", case_id,
                json.dumps({"title": case_data["title"]})
            )

            # Get documents for this case type
            case_docs = DOCUMENTS.get(case_data["type"], {})

            for doc_name, doc_content in case_docs.items():
                # Determine document type
                if "transcript" in doc_name:
                    doc_type = "transcript"
                elif "policy" in doc_name:
                    doc_type = "policy"
                elif "email" in doc_name:
                    doc_type = "email"
                else:
                    doc_type = "other"

                filename = f"{doc_name}.txt"

                # Create document
                doc_row = await conn.fetchrow(
                    """
                    INSERT INTO er_case_documents
                    (case_id, document_type, filename, file_path, mime_type, file_size,
                     pii_scrubbed, original_text, scrubbed_text, processing_status, uploaded_by, parsed_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                    RETURNING id
                    """,
                    case_id, doc_type, filename, f"er-cases/{case_id}/{filename}",
                    "text/plain", len(doc_content), True, doc_content, doc_content,
                    "completed", admin_id
                )
                doc_id = str(doc_row["id"])
                print(f"    Added document: {filename}")

                # Log document upload
                await conn.execute(
                    """
                    INSERT INTO er_audit_log (case_id, user_id, action, entity_type, entity_id, details)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    case_id, admin_id, "document_uploaded", "document", doc_id,
                    json.dumps({"filename": filename, "document_type": doc_type})
                )

                # Create evidence chunks (simple splitting by paragraphs)
                paragraphs = [p.strip() for p in doc_content.split("\n\n") if p.strip()]
                for idx, para in enumerate(paragraphs[:10]):  # Limit to 10 chunks per doc
                    if len(para) < 50:
                        continue

                    # Extract speaker if present (for transcripts)
                    speaker = None
                    if ":" in para and doc_type == "transcript":
                        potential_speaker = para.split(":")[0].strip()
                        if len(potential_speaker) < 50 and potential_speaker.isupper():
                            speaker = potential_speaker

                    # Create zero vector for embedding (768 dimensions)
                    zero_vector = "[" + ",".join(["0"] * 768) + "]"

                    await conn.execute(
                        """
                        INSERT INTO er_evidence_chunks
                        (document_id, case_id, chunk_index, content, speaker, embedding, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6::vector, $7)
                        """,
                        doc_id, case_id, idx, para[:500], speaker, zero_vector,
                        json.dumps({"char_start": 0, "source_file": filename})
                    )

            # Create analysis results
            case_type = case_data["type"]

            # Timeline analysis
            timeline = create_timeline_analysis(case_type)
            await conn.execute(
                """
                INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, generated_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (case_id, analysis_type) DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                case_id, "timeline", json.dumps(timeline), admin_id
            )
            print(f"    Added timeline analysis")

            # Discrepancy analysis
            discrepancies = create_discrepancy_analysis(case_type)
            await conn.execute(
                """
                INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, generated_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (case_id, analysis_type) DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                case_id, "discrepancies", json.dumps(discrepancies), admin_id
            )
            print(f"    Added discrepancy analysis")

            # Policy check analysis
            policy = create_policy_analysis(case_type)
            await conn.execute(
                """
                INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, generated_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (case_id, analysis_type) DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                case_id, "policy_check", json.dumps(policy), admin_id
            )
            print(f"    Added policy check analysis")

            # Log analysis generation
            await conn.execute(
                """
                INSERT INTO er_audit_log (case_id, user_id, action, details)
                VALUES ($1, $2, $3, $4)
                """,
                case_id, admin_id, "analysis_generated",
                json.dumps({"types": ["timeline", "discrepancies", "policy_check"]})
            )

            created_cases.append({
                "id": case_id,
                "case_number": case_row["case_number"],
                "title": case_data["title"]
            })

        print("\n" + "=" * 60)
        print("SEED COMPLETE")
        print("=" * 60)
        print(f"\nCreated {len(created_cases)} ER investigation cases:\n")
        for case in created_cases:
            print(f"  [{case['case_number']}] {case['title']}")

        print(f"\nView at: http://localhost:5174/app/er-copilot")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed_er_copilot())
