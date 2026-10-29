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
import { useSchedulingPrice } from './useSchedulingPrice'

/** `/scheduling` — the scheduling product page. */
export default function SchedulingTab({ onContact }: { onContact: () => void }) {
  useHashScroll()
  // One fetch for every price on the page: the product "Start now" buys.
  const livePrice = useSchedulingPrice()
  return (
    <>
      <BuyerTopBar />
      <TimelineRail darkStep="cost" />
      <Hero onContact={onContact} showCommercial />
      <main>
        <BuyerGuide livePrice={livePrice} />
        <Draft />
        <Check />
        <Change />
        <Recovery />
        <Cost />
        <Publish />
        <Setup onContact={onContact} />
        <OperationFit />
        <Value onContact={onContact} livePrice={livePrice} />
        <Pricing onContact={onContact} livePrice={livePrice} />
        <BuyerQuestions onContact={onContact} />
        <Closing onContact={onContact} />
      </main>
    </>
  )
}
