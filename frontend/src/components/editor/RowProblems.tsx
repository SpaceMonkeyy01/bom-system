export function RowProblems({ messages }: { messages: string[] | undefined }) {
  if (!messages?.length) return null
  return (
    <div className="line-error" role="alert">
      {messages.map((m) => (
        <div key={m}>{m}</div>
      ))}
    </div>
  )
}
