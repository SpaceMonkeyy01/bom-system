import { Anchor, Group, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { status, type Tone } from '../theme'

export type { Tone }

/** A status word on its soft fill: 24px high, pill text style. */
export function StatusPill({ tone, children, className, title }: { tone: Tone; children: ReactNode; className?: string; title?: string }) {
  const [color, background] = status[tone]
  return (
    <span className={`pill${className ? ` ${className}` : ''}`} style={{ color, background }} title={title}>
      {children}
    </span>
  )
}

/** The same at 20px, for rate sources and checklist tags. */
export function RateTag({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  const [color, background] = status[tone]
  return (
    <span className="tag" style={{ color, background }} title={title}>
      {children}
    </span>
  )
}

interface HeroProps {
  value: ReactNode
  tone?: Tone | 'ink'
  sentence: ReactNode
  caption?: ReactNode
  captionTone?: Tone
  to?: string
  testId?: string
}

/** A number as a sentence: "3 orders need a BOM". Renders as a link to its list when `to` is given. */
export function HeroNumber({ value, tone = 'ink', sentence, caption, captionTone, to, testId }: HeroProps) {
  const color = tone === 'ink' ? undefined : status[tone][0]
  const body = (
    <>
      <span className="hero-value" style={{ color }}>
        {value}
      </span>
      <span>{sentence}</span>
      {caption && (
        <span className="caption" style={captionTone ? { color: status[captionTone][0], fontWeight: 700 } : undefined}>
          {caption}
        </span>
      )}
    </>
  )
  if (to) {
    return (
      <Link to={to} className="hero" data-testid={testId}>
        {body}
      </Link>
    )
  }
  return (
    <div className="hero" data-testid={testId}>
      {body}
    </div>
  )
}

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Pills shown beside the title. */
  pills?: ReactNode
  actions?: ReactNode
  crumbs?: { label: string; to?: string }[]
}

export function PageHeader({ title, description, pills, actions, crumbs }: PageHeaderProps) {
  return (
    <div className="page-header-wrap">
      {crumbs && (
        <nav aria-label="Breadcrumb" className="crumbs">
          {crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && ' / '}
              {c.to ? (
                <Anchor component={Link} to={c.to} size="xs">
                  {c.label}
                </Anchor>
              ) : (
                c.label
              )}
            </span>
          ))}
        </nav>
      )}
      <header className="page-header">
        <div className="page-header-text">
          <Group gap="md" wrap="wrap" align="center">
            <Title order={1}>{title}</Title>
            {pills}
          </Group>
          {description && (
            <Text c="var(--slate)" size="sm">
              {description}
            </Text>
          )}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </header>
    </div>
  )
}

/** A bordered section of the sheet with a header row. */
export function Section({ title, meta, right, children, className, id, padded = true }: { title?: ReactNode; meta?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; id?: string; padded?: boolean }) {
  return (
    <section className={`card${className ? ` ${className}` : ''}`} aria-labelledby={id} data-testid={id}>
      {(title || right) && (
        <div className="card-head">
          {title && (
            <Title order={2} id={id}>
              {title}
            </Title>
          )}
          {meta && <span className="caption">{meta}</span>}
          {right && <div className="card-head-right">{right}</div>}
        </div>
      )}
      <div className={padded ? 'card-body' : undefined}>{children}</div>
    </section>
  )
}
