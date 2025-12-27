"""PII Scrubbing Service for ER Copilot.

Detects and replaces Personally Identifiable Information (PII) before
sending documents to LLMs for analysis.
"""

import re
from typing import Optional


class PIIScrubber:
    """Detect and replace PII in text before LLM processing."""

    # Regex patterns for common PII types
    PATTERNS = {
        "ssn": (
            r"\b\d{3}-\d{2}-\d{4}\b",
            "[SSN-REDACTED]"
        ),
        "ssn_no_dash": (
            r"\b\d{9}\b",
            "[SSN-REDACTED]"
        ),
        "email": (
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "[EMAIL-REDACTED]"
        ),
        "phone_us": (
            r"\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b",
            "[PHONE-REDACTED]"
        ),
        "dob_mdy": (
            r"\b(0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])[-/](19|20)\d{2}\b",
            "[DOB-REDACTED]"
        ),
        "dob_ymd": (
            r"\b(19|20)\d{2}[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b",
            "[DOB-REDACTED]"
        ),
        "credit_card": (
            r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            "[CC-REDACTED]"
        ),
        "bank_account": (
            r"\b\d{8,17}\b",
            None  # Skip - too many false positives
        ),
        "drivers_license": (
            r"\b[A-Z]{1,2}\d{6,8}\b",
            "[DL-REDACTED]"
        ),
        "passport": (
            r"\b[A-Z]{1,2}\d{6,9}\b",
            "[PASSPORT-REDACTED]"
        ),
        "address_street": (
            r"\b\d{1,5}\s+(?:[A-Za-z]+\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way|Place|Pl)\.?\b",
            "[ADDRESS-REDACTED]"
        ),
        "zip_code": (
            r"\b\d{5}(?:-\d{4})?\b",
            "[ZIP-REDACTED]"
        ),
    }

    def __init__(
        self,
        preserve_names: Optional[list[str]] = None,
        custom_patterns: Optional[dict[str, tuple[str, str]]] = None,
        skip_patterns: Optional[list[str]] = None,
    ):
        """
        Initialize the PII scrubber.

        Args:
            preserve_names: Names to keep (e.g., employees involved in investigation).
                           These will NOT be scrubbed.
            custom_patterns: Additional patterns to scrub {name: (regex, replacement)}.
            skip_patterns: Pattern names from PATTERNS to skip.
        """
        self.preserve_names = set(n.lower() for n in (preserve_names or []))
        self.skip_patterns = set(skip_patterns or [])
        self.replacement_map: dict[str, str] = {}
        self._counter: dict[str, int] = {}

        # Merge custom patterns
        self.patterns = dict(self.PATTERNS)
        if custom_patterns:
            self.patterns.update(custom_patterns)

    def _get_replacement(self, match: str, pattern_name: str) -> str:
        """Get or create a unique replacement for a matched PII value."""
        if match in self.replacement_map:
            return self.replacement_map[match]

        # Create unique replacement
        self._counter.setdefault(pattern_name, 0)
        self._counter[pattern_name] += 1
        replacement = f"[{pattern_name.upper()}-{self._counter[pattern_name]}]"
        self.replacement_map[match] = replacement
        return replacement

    def scrub(self, text: str) -> tuple[str, dict[str, str]]:
        """
        Scrub PII from text.

        Args:
            text: The text to scrub.

        Returns:
            Tuple of (scrubbed_text, replacement_map).
            The replacement_map can be used to restore original values if needed.
        """
        scrubbed = text
        self.replacement_map = {}
        self._counter = {}

        for pattern_name, (pattern, default_replacement) in self.patterns.items():
            # Skip if in skip list or no default replacement
            if pattern_name in self.skip_patterns or default_replacement is None:
                continue

            def replace_fn(match: re.Match) -> str:
                matched = match.group(0)
                # Check if it's a preserved name
                if matched.lower() in self.preserve_names:
                    return matched
                return self._get_replacement(matched, pattern_name)

            scrubbed = re.sub(pattern, replace_fn, scrubbed)

        return scrubbed, self.replacement_map

    def scrub_names(
        self,
        text: str,
        names_to_redact: list[str],
        preserve_names: Optional[list[str]] = None,
    ) -> tuple[str, dict[str, str]]:
        """
        Scrub specific names from text.

        Args:
            text: The text to scrub.
            names_to_redact: List of names to redact.
            preserve_names: Names to preserve (e.g., investigators).

        Returns:
            Tuple of (scrubbed_text, replacement_map).
        """
        scrubbed = text
        name_map: dict[str, str] = {}
        preserve_set = set(n.lower() for n in (preserve_names or []))

        for i, name in enumerate(names_to_redact, 1):
            if name.lower() in preserve_set:
                continue

            replacement = f"[PERSON-{i}]"
            name_map[name] = replacement

            # Case-insensitive replacement
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            scrubbed = pattern.sub(replacement, scrubbed)

        return scrubbed, name_map

    def restore(self, scrubbed_text: str, replacement_map: dict[str, str]) -> str:
        """
        Restore original values from a scrubbed text.

        Args:
            scrubbed_text: The scrubbed text.
            replacement_map: The map from original values to replacements.

        Returns:
            The text with original values restored.
        """
        restored = scrubbed_text
        # Reverse the replacement map
        reverse_map = {v: k for k, v in replacement_map.items()}

        for replacement, original in reverse_map.items():
            restored = restored.replace(replacement, original)

        return restored

    @staticmethod
    def detect_pii(text: str) -> dict[str, list[str]]:
        """
        Detect PII in text without scrubbing.

        Args:
            text: The text to analyze.

        Returns:
            Dictionary of pattern_name -> list of matches.
        """
        found: dict[str, list[str]] = {}

        for pattern_name, (pattern, _) in PIIScrubber.PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                found[pattern_name] = matches

        return found

    @staticmethod
    def has_pii(text: str) -> bool:
        """
        Quick check if text contains any PII.

        Args:
            text: The text to check.

        Returns:
            True if any PII patterns are detected.
        """
        for pattern, _ in PIIScrubber.PATTERNS.values():
            if re.search(pattern, text):
                return True
        return False
