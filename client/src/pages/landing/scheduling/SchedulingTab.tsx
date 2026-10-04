import { Change } from './sections/Change'
import { Check } from './sections/Check'
import { Closing } from './sections/Closing'
import { Cost } from './sections/Cost'
import { Draft } from './sections/Draft'
import { TimelineRail } from './sections/Chrome'
import { Hero } from './sections/Hero'
import { Publish } from './sections/Publish'
import { BuyerGuide, BuyerQuestions, BuyerTopBar, OperationFit, Recovery, Setup } from './buyers/BuyerSections'
import { Pricing } from './buyers/Pricing'
import { Value } from './buyers/Value'
import { useHashScroll } from './useHashScroll'

/** `/` — the scheduling home page. */
export default function SchedulingTab({ onContact }: { onContact: () => void }) {
  useHashScroll()
  return (
    <>
      <BuyerTopBar />
      <TimelineRail darkStep="cost" />
      <Hero onContact={onContact} showCommercial />
      <main>
        <BuyerGuide />
        <Draft />
        <Check />
        <Change />
        <Recovery />
        <Cost />
        <Publish />
        <Setup onContact={onContact} />
        <OperationFit />
        <Value onContact={onContact} />
        <Pricing onContact={onContact} />
        <BuyerQuestions onContact={onContact} />
        <Closing onContact={onContact} />
      </main>
    </>
  )
}
