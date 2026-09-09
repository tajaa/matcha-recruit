"""Errors an operator can recover from through the manager."""

import subprocess

RECOVERABLE_ERRORS = (KeyError, OSError, RuntimeError, ValueError, subprocess.SubprocessError)
