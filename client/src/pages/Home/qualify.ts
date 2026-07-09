// Shared between the hero email modal and the /start questions page.

export const QUALIFY_EMAIL_KEY = "matcha_qualify_email";

// Kept in sync with FREE_EMAIL_DOMAINS in server/app/core/routes/resources.py.
// The server is authoritative — this list only exists so the visitor gets the
// error before a round trip. A domain missing here is still rejected on submit.
const FREE_EMAIL_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "ymail.com",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "msn.com",
  "icloud.com",
  "me.com",
  "mac.com",
  "aol.com",
  "gmx.com",
  "mail.com",
  "protonmail.com",
  "proton.me",
  "pm.me",
  "yandex.com",
  "zoho.com",
  "fastmail.com",
  "hey.com",
  "qq.com",
  "comcast.net",
  "verizon.net",
  "att.net",
]);

/** Returns an error string, or null when the address is a usable work email. */
export function validateWorkEmail(raw: string): string | null {
  const value = raw.trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
    return "Enter a valid email address.";
  }
  if (FREE_EMAIL_DOMAINS.has(value.split("@")[1])) {
    return "Please use your work email — personal mailboxes aren't accepted.";
  }
  return null;
}

export const HEADCOUNT_OPTIONS = [
  { value: "1-24", label: "1 – 24", hint: "Getting the basics right" },
  { value: "25-99", label: "25 – 99", hint: "First real HR obligations" },
  { value: "100-299", label: "100 – 299", hint: "OSHA logs, multi-state" },
  { value: "300-999", label: "300 – 999", hint: "Dedicated risk function" },
  { value: "1000+", label: "1,000+", hint: "Enterprise exposure" },
];

export const LOCATION_OPTIONS = [
  { value: "1", label: "One", hint: "Single site" },
  { value: "2-4", label: "2 – 4", hint: "A few sites" },
  { value: "5-9", label: "5 – 9", hint: "Multi-state likely" },
  { value: "10+", label: "10+", hint: "Distributed footprint" },
];

export const NEED_OPTIONS = [
  { value: "workplace_safety", label: "Workplace safety & incidents" },
  { value: "compliance", label: "Multi-state compliance" },
  { value: "employee_relations", label: "Employee relations" },
  { value: "hr_operations", label: "HR operations" },
  { value: "legal_exposure", label: "Legal exposure" },
  { value: "not_sure", label: "Not sure yet" },
];
