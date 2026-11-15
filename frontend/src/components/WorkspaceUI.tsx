import { useEffect, useRef, type ReactNode } from 'react'

export function Brand() {
  return <span className="brand"><span className="brand-mark" aria-hidden="true">R</span>RaceSafe</span>
}

export function Avatar({ name, tone = 0 }: { name: string; tone?: number }) {
  return <span className={'avatar tone-' + (tone % 4)} aria-hidden="true">{Array.from(name)[0]?.toUpperCase()}</span>
}

export function Skills({ items, limit = items.length }: { items: string[]; limit?: number }) {
  if (items.length === 0) return null
  return (
    <ul className="tags" aria-label="Skills">
      {items.slice(0, limit).map((skill) => <li key={skill}>{skill}</li>)}
      {items.length > limit && <li aria-label={(items.length - limit) + ' more skills'}>+{items.length - limit}</li>}
    </ul>
  )
}

export function Dialog({ title, onDismiss, children }: {
  title: string; onDismiss: () => void; children: ReactNode
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = dialog.current
    const trigger = document.activeElement
    node?.showModal()
    return () => {
      node?.close()
      if (trigger instanceof HTMLElement && trigger.isConnected) {
        trigger.focus({ preventScroll: true })
      }
    }
  }, [])

  return (
    <dialog ref={dialog} aria-label={title} onCancel={(event) => {
      event.preventDefault()
      onDismiss()
    }}>
      <h2>{title}</h2>
      {children}
    </dialog>
  )
}
