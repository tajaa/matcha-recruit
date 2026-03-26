import { Link } from 'react-router-dom'

type LogoProps = {
  to?: string
  label?: string
  className?: string
}

export function Logo({ to = '/', label = 'Matcha', className = '' }: LogoProps) {
  const content = (
    <>
      <img src="/logo.svg" alt="Matcha" className="h-7 w-7" />
      <span className="text-sm font-semibold text-zinc-100">
        {label}
      </span>
    </>
  )

  return (
    <Link to={to} className={`flex items-center gap-2.5 ${className}`}>
      {content}
    </Link>
  )
}
