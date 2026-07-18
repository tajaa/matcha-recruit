import { BarChart3, Download, FileSpreadsheet, GitCompare, Wand2 } from 'lucide-react'
import type { HowItWorksStep } from '../../../components/ui/HowItWorksModal'

export const HOW_IT_WORKS_STEPS: HowItWorksStep[] = [
  {
    icon: FileSpreadsheet,
    title: 'Upload your data',
    body: 'CSV, XLSX, or a financial-document PDF — a P&L, 10-K, loss run, inventory list. If a document needs AI extraction, you confirm the extracted figures before any analysis runs.',
    detail: "A document's extraction is parsed once and never re-guessed — you're always confirming real figures, not a fresh interpretation.",
  },
  {
    icon: BarChart3,
    title: 'Deterministic metrics, computed for you',
    body: 'Analyzer packs — general stats, volatility & risk, financial ratios, insurance loss, inventory ops — compute real numbers from your data automatically. See them all in the Metrics tab.',
    detail: 'Every metric is computed in Python from your values, so the same data always yields the same numbers — nothing is estimated by the AI.',
  },
  {
    icon: Wand2,
    title: 'Ask the analyst — everything is cited',
    body: 'Every number in a reply traces back to a computed record. Click any record in the Metrics tab to focus your next question on it.',
    detail: "Anything the pilot can't trace to a real computed record is dropped from its answer, so a cited figure is always one that exists.",
  },
  {
    icon: GitCompare,
    title: 'Compare datasets',
    body: 'Pick two or more datasets to see side-by-side deltas, percent change, and CAGR.',
    detail: 'Select datasets in the order you want them read — the comparison runs left-to-right from your selection, so the first is the baseline.',
  },
  {
    icon: Download,
    title: 'Export the analyst report',
    body: 'One click renders a PDF with inline charts, built from the metrics and the conversation you have already had — not regenerated from scratch.',
    detail: 'The report is assembled from the stored computed numbers and your chat, so what you export matches exactly what you reviewed on screen.',
  },
]
