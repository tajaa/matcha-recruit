"Gemini false-positive" — the on-create AI extraction reads the narrative and sets a signal that isn't really
true. Example: narrative says "needlestick from a new, unused needle" → Gemini sets contaminated_sharps: true.
Or "the patient in 204 has TB" → Gemini sets infectious_agent: tuberculosis even though the employee wasn't
exposed. Result: that row gets masked → shows "Privacy Case" instead of the real name, when arguably it
shouldn't.

"Masks conservatively (privacy-safe direction)" — the error can only go ONE way. The AI only adds positive
signals; it never unsets one, and the merge keeps any human-entered value. So an AI mistake can only over-mask
(hide a name that could've shown), never under-mask (leak a name that must be hidden). Over-hiding is the
safe failure for PHI — you'd rather redact too much than leak. The dangerous direction can't happen from an AI
error.

And the name isn't lost: it's still in the DB and resolvable by admin/client via /osha/privacy-cases. A
wrongly-masked row → the compliance officer still sees who it is. Nothing destroyed.

"No post-create un-flag UI" — the asymmetry:

- Signals you set in the create modal are in category_data at insert; the merge (existing wins) means the AI
  can't override them. So at creation, you win.
- But the AI runs after submit. If you left a signal blank and the AI sets it wrong, category_data now carries
  contaminated_sharps: true — and there's no control anywhere to flip it back off. The create modal is
  create-only (incident already exists); the detail page has no privacy-signal toggle. So correcting a wrong AI
  flag today means editing category_data in the DB by hand.

"Manual correction today is at creation" — you can pre-set the signals correctly when filing (and those
stick), but you can't fix the AI's guess afterward through the app.

The follow-up — a small detail-page (or Copilot) editor: show the privacy signals + the masked reason, let a
compliance user toggle them — un-flag a false positive, flag a miss. Minor because the failure is already
privacy-safe and the name is always recoverable; it's a correctness/UX nicety, not a leak risk.
