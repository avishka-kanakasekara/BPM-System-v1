import { Link } from 'react-router-dom'

type AccessDeniedProps = {
  title?: string
  message: string
  homeTo?: string
}

/** Reusable unauthorized state — no sensitive implementation details. */
export default function AccessDenied({
  title = 'Access denied',
  message,
  homeTo = '/',
}: AccessDeniedProps) {
  return (
    <section
      role="alert"
      className="mx-auto max-w-lg rounded-xl border border-slate-200 bg-white px-6 py-10 text-center shadow-sm"
    >
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">{message}</p>
      <Link to={homeTo} className="btn btn-primary btn-sm mt-6">
        Back to dashboard
      </Link>
    </section>
  )
}
