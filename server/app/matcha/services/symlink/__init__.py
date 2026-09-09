"""Sym-link — bounded, guided task links.

Package map (see CLAUDE.md in this directory):
  kinds.py        built-in kind registry + spec materialization (pure)
  passcode.py     weekly company passcode: generate / verify / rotation math + DB
  chat.py         the per-turn Gemini engine — pure function, deterministic completion
  links.py        symlinks / symlink_unlocks DB service
  attachments.py  S3 staging for recipient uploads
  submissions.py  stage + per-kind apply (confirm-first)
  notify.py       recipient / sender emails + channel rotation announcement
"""
