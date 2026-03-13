import { useState, useMemo, useCallback } from 'react';
import type { ERInvolvedEmployee, EREmployeeRole } from '../../types';

interface ReplacementRule {
  pattern: RegExp;
  replacement: string;
}

interface LegendEntry {
  pseudonym: string;
  role: string;
}

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

const ROLE_LABELS: Record<EREmployeeRole, string> = {
  complainant: 'Complainant',
  respondent: 'Respondent',
  witness: 'Witness',
};

function storageKey(caseId: string) {
  return `er-blinded-${caseId}`;
}

export function useBlindedMode(
  caseId: string,
  involvedEmployees: ERInvolvedEmployee[],
  companyEmployees: { id: string; first_name: string; last_name: string }[],
) {
  const [isBlinded, setIsBlinded] = useState(() => {
    if (!caseId) return false;
    try {
      return localStorage.getItem(storageKey(caseId)) === '1';
    } catch {
      return false;
    }
  });

  const toggleBlinded = useCallback(() => {
    setIsBlinded((prev) => {
      const next = !prev;
      try {
        if (next) {
          localStorage.setItem(storageKey(caseId), '1');
        } else {
          localStorage.removeItem(storageKey(caseId));
        }
      } catch {
        // storage unavailable
      }
      return next;
    });
  }, [caseId]);

  const { rules, pseudonymMap, legend } = useMemo(() => {
    const sorted = [...involvedEmployees].sort((a, b) =>
      a.employee_id.localeCompare(b.employee_id),
    );

    const pMap = new Map<string, string>();
    const legendEntries: LegendEntry[] = [];
    const replacementRules: { text: string; replacement: string }[] = [];

    // Count first/last names among involved to decide uniqueness
    const firstNameCounts = new Map<string, number>();
    const lastNameCounts = new Map<string, number>();

    const resolvedNames: { id: string; first: string; last: string; role: EREmployeeRole }[] = [];

    sorted.forEach((ie) => {
      const emp = companyEmployees.find((e) => e.id === ie.employee_id);
      if (!emp) return;
      const first = emp.first_name.trim();
      const last = emp.last_name.trim();
      resolvedNames.push({ id: ie.employee_id, first, last, role: ie.role });
      firstNameCounts.set(first.toLowerCase(), (firstNameCounts.get(first.toLowerCase()) || 0) + 1);
      lastNameCounts.set(last.toLowerCase(), (lastNameCounts.get(last.toLowerCase()) || 0) + 1);
    });

    resolvedNames.forEach((r, idx) => {
      if (idx >= 26) return;
      const pseudonym = `Person ${LETTERS[idx]}`;
      pMap.set(r.id, pseudonym);
      legendEntries.push({ pseudonym, role: ROLE_LABELS[r.role] });

      // Full name
      const fullName = `${r.first} ${r.last}`;
      replacementRules.push({ text: fullName, replacement: pseudonym });

      // Last name if unique among involved
      if (r.last && (lastNameCounts.get(r.last.toLowerCase()) || 0) <= 1) {
        replacementRules.push({ text: r.last, replacement: pseudonym });
      }

      // First name if unique among involved
      if (r.first && (firstNameCounts.get(r.first.toLowerCase()) || 0) <= 1) {
        replacementRules.push({ text: r.first, replacement: pseudonym });
      }
    });

    // Sort longest-first to avoid partial clobber
    replacementRules.sort((a, b) => b.text.length - a.text.length);

    const compiled: ReplacementRule[] = replacementRules.map((r) => ({
      pattern: new RegExp(`\\b${escapeRegex(r.text)}(?:'s)?\\b`, 'gi'),
      replacement: r.replacement,
    }));

    return { rules: compiled, pseudonymMap: pMap, legend: legendEntries };
  }, [involvedEmployees, companyEmployees]);

  const blindText = useCallback(
    (text: string): string => {
      if (!isBlinded || !text) return text;
      let result = text;
      for (const rule of rules) {
        result = result.replace(rule.pattern, rule.replacement);
      }
      return result;
    },
    [isBlinded, rules],
  );

  const getPseudonym = useCallback(
    (employeeId: string): string => {
      if (!isBlinded) return '';
      return pseudonymMap.get(employeeId) || '';
    },
    [isBlinded, pseudonymMap],
  );

  return { isBlinded, toggleBlinded, blindText, getPseudonym, legend };
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
