import type { GlossaryTerm } from './glossary/types'
import { GLOSSARY_LAW } from './glossary/law'
import { GLOSSARY_AGENCY } from './glossary/agency'
import { GLOSSARY_CONCEPT } from './glossary/concept'
import { GLOSSARY_TAX } from './glossary/tax'
import { GLOSSARY_LEAVE } from './glossary/leave'
import { GLOSSARY_COMP } from './glossary/comp'

export type { GlossaryTerm } from './glossary/types'
export { CATEGORIES_LABEL } from './glossary/categories'

export const GLOSSARY: GlossaryTerm[] = [
  ...GLOSSARY_LAW,
  ...GLOSSARY_AGENCY,
  ...GLOSSARY_CONCEPT,
  ...GLOSSARY_TAX,
  ...GLOSSARY_LEAVE,
  ...GLOSSARY_COMP,
]
