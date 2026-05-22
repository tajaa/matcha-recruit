import HeadlinesPanel from '../../components/resources-free/HeadlinesPanel'

export default function ResourcesHeadlines() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">This week in HR</h1>
        <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
          Industry headlines from the last 7 days
        </p>
      </div>
      <HeadlinesPanel />
    </div>
  )
}
