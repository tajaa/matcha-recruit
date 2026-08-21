# Operational Mode Awareness

At the start of every user turn, inspect the current system-provided operational mode. The mode can change during an existing session; never infer the current mode from an earlier turn.

- In `plan` mode, remain read-only and do not edit files, run mutating commands, or claim implementation is complete.
- In `build` mode, implement the user's requested changes and run appropriate verification. A later system reminder that the mode changed to `build` overrides any earlier plan-mode restriction immediately.
- If the mode changed since the previous turn, adapt in the current turn without asking the user to switch modes again.
- Before refusing an implementation request because of plan-mode restrictions, verify that the latest system message still identifies the session as `plan`.
