import type { SVGProps } from 'react'

type ArtworkProps = SVGProps<SVGSVGElement>

export function StudioReceiptIllustration(props: ArtworkProps) {
  return (
    <svg viewBox="0 0 260 180" fill="none" aria-hidden="true" {...props}>
      <path d="M31 24.5 213 9l15 132.5-182 15.5L31 24.5Z" fill="#EFE5D3" stroke="#292722" strokeWidth="2" />
      <path d="m42 38 161-13.5M45 53l91-7.5M47 65.5l70-6M50 94l118-10M52 108l78-6.5" stroke="#8D8376" strokeWidth="2" strokeLinecap="round" />
      <path d="m47 122 73-6.5" stroke="#B86612" strokeWidth="4" strokeLinecap="round" />
      <path d="m170.5 98.5 30.6 30.6M201.1 98.5l-30.6 30.6" stroke="#B86612" strokeWidth="3" strokeLinecap="round" />
      <path d="M161 45h38v38h-38V45Z" fill="#FFF9EF" stroke="#292722" strokeWidth="2" />
      <path d="M166 50h8v8h-8v-8ZM186 50h8v8h-8v-8ZM166 70h8v8h-8v-8ZM181 62h5v5h-5v-5ZM190 70h4v8h-4v-8Z" fill="#292722" />
      <path d="m224 126 12 8-10 3 1 11-8-8-9 5 3-10-9-6 11-1 3-10 6 8Z" fill="#D98525" stroke="#292722" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  )
}

export function StudioBoardIllustration(props: ArtworkProps) {
  return (
    <svg viewBox="0 0 180 120" fill="none" aria-hidden="true" {...props}>
      <path d="M25 22h111v77H25V22Z" fill="#8C7051" stroke="#3E2F20" strokeWidth="2" />
      <path d="m37 37 35-5 4 29-35 5-4-29ZM88 30l35 5-4 29-35-5 4-29ZM47 76l37-4 3 18-37 4-3-18Z" fill="#F8E6C6" stroke="#3E2F20" strokeWidth="1.5" />
      <circle cx="55" cy="35" r="4" fill="#D98525" stroke="#3E2F20" strokeWidth="1.5" />
      <circle cx="106" cy="36" r="4" fill="#D98525" stroke="#3E2F20" strokeWidth="1.5" />
      <circle cx="67" cy="74" r="4" fill="#D98525" stroke="#3E2F20" strokeWidth="1.5" />
      <path d="M14 101h137" stroke="#3E2F20" strokeWidth="2" strokeLinecap="round" />
      <path d="M19 18 12 9M143 18l8-9" stroke="#D98525" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function StudioRegisterIllustration(props: ArtworkProps) {
  return (
    <svg viewBox="0 0 120 92" fill="none" aria-hidden="true" {...props}>
      <rect x="15" y="13" width="90" height="62" rx="4" fill="#FFF9EF" stroke="#292722" strokeWidth="2" />
      <path d="M25 27h70M25 38h28M25 49h44M25 60h19" stroke="#B5AA9C" strokeWidth="3" strokeLinecap="round" />
      <path d="M75 38h20v22H75V38Z" fill="#F0E3D0" stroke="#B86612" strokeWidth="2" />
      <path d="M80 43h10M80 49h10M80 55h6" stroke="#B86612" strokeWidth="2" strokeLinecap="round" />
      <path d="m41 82 7-7h24l7 7" stroke="#292722" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
