import { Alert, Anchor, Badge, Button, Group, List, Modal, Paper, Text, Textarea, Title } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { CostHead, Problem, Template, Uom } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { LinesTable } from '../components/editor/LinesTable'
import { ParamsTable } from '../components/editor/ParamsTable'
import { TemplatePreview } from '../components/editor/TemplatePreview'
import { PageError, PageLoader } from '../components/PageState'
import { type Draft, draftFromTemplate, indexProblems, toBody } from '../lib/templates'

const VALIDATE_DEBOUNCE_MS = 400

export function TemplateEditorPage() {
  const templateId = Number(useParams().templateId)
  const template = useQuery({
    queryKey: ['template', templateId],
    queryFn: ({ signal }) => api<Template>(`/templates/${templateId}`, { signal }),
  })
  if (template.isPending) return <PageLoader />
  if (template.isError) return <PageError title="Couldn’t load this template" error={template.error} />
  // Remounts when the saved template changes identity, which only happens on navigation.
  return <Editor key={templateId} initial={template.data} />
}

function Editor({ initial }: { initial: Template }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEditTemplates } = useAuth()
  const [saved, setSaved] = useState(initial)
  const [draft, setDraft] = useState<Draft>(() => draftFromTemplate(initial))
  const [dirty, setDirty] = useState(false)
  const [revision, setRevision] = useState(0)
  const [notice, setNotice] = useState<{ color: string; text: string } | null>(null)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const readOnly = !canEditTemplates || saved.status !== 'draft'

  const costHeads = useQuery({ queryKey: ['cost-heads'], queryFn: ({ signal }) => api<CostHead[]>('/cost-heads', { signal }), staleTime: 5 * 60_000 })
  const uoms = useQuery({ queryKey: ['uoms'], queryFn: ({ signal }) => api<Uom[]>('/uoms', { signal }), staleTime: 5 * 60_000 })

  const change = useCallback((next: (d: Draft) => Draft) => {
    setDraft(next)
    setDirty(true)
  }, [])

  // Validation runs on every pause in typing; it never saves.
  const body = useMemo(() => toBody(draft), [draft])
  const [debouncedBody] = useDebouncedValue(body, VALIDATE_DEBOUNCE_MS)
  const validation = useQuery({
    queryKey: ['template-validate', debouncedBody],
    queryFn: ({ signal }) => api<Problem[]>('/templates/validate', { json: debouncedBody, signal }),
    enabled: !readOnly,
    placeholderData: (prev) => prev,
    gcTime: 0,
  })
  const problems = useMemo(() => indexProblems(validation.data ?? []), [validation.data])
  const problemCount = validation.data?.length ?? 0

  const save = useMutation({
    mutationFn: () => api<{ template: Template; problems: Problem[] }>(`/templates/${saved.id}`, { method: 'PUT', json: body }),
    onSuccess: ({ template }) => {
      setSaved(template)
      setDirty(false)
      setRevision((r) => r + 1)
      setNotice(null)
      queryClient.setQueryData(['template', template.id], template)
      for (const key of ['sign-type-versions', 'sign-type-templates', 'flagged']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: (e) => setNotice({ color: 'red', text: `Couldn’t save: ${errorMessage(e)}` }),
  })

  const publish = useMutation({
    mutationFn: async () => {
      if (dirty) await save.mutateAsync()
      return api<Template>(`/templates/${saved.id}/publish`, { method: 'POST' })
    },
    onSuccess: (template) => {
      setSaved(template)
      setDraft(draftFromTemplate(template))
      setDirty(false)
      setNotice({ color: 'green', text: `Published as v${template.version}. Create BOM now uses it for ${template.sign_type_name}.` })
      queryClient.setQueryData(['template', template.id], template)
      for (const key of ['sign-types', 'sign-type-versions', 'sign-type-templates', 'flagged', 'bom-preview']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: (e) => setNotice({ color: 'red', text: errorMessage(e) }),
  })

  const discard = useMutation({
    mutationFn: () => api<void>(`/templates/${saved.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['template', saved.id] })
      for (const key of ['sign-types', 'sign-type-versions', 'sign-type-templates', 'flagged']) queryClient.invalidateQueries({ queryKey: [key] })
      navigate('/templates')
    },
    onError: (e) => setNotice({ color: 'red', text: errorMessage(e) }),
  })

  // Ctrl/Cmd+S saves; closing the tab with unsaved edits asks first.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (!readOnly && dirty && !save.isPending) save.mutate()
      }
    }
    const onUnload = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('beforeunload', onUnload)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('beforeunload', onUnload)
    }
  }, [dirty, readOnly, save])

  const paramNames = draft.parameters.map((p) => p.param_name.trim()).filter(Boolean)
  const flagged = draft.lines.filter((l) => l.notes).length
  const busy = save.isPending || publish.isPending || discard.isPending

  return (
    <div className="editor-page">
      <Paper withBorder className="bom-bar editor-bar">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <Anchor component={Link} to="/templates" size="xs" className="nowrap">
            Templates
          </Anchor>
          <Text size="xs" c="dimmed">
            /
          </Text>
          <Anchor component={Link} to={`/sign-types/${saved.sign_type_id}`} size="sm" fw={700} className="nowrap" truncate>
            {saved.sign_type_name}
          </Anchor>
          <Text size="sm" fw={700} className="nowrap">
            v{saved.version}
          </Text>
          <Badge size="sm" variant="light" color={saved.status === 'published' ? 'green' : saved.status === 'draft' ? 'blue' : 'gray'} tt="none">
            {saved.status}
          </Badge>
          {saved.source && (
            <Text size="xs" c="dimmed" className="nowrap" visibleFrom="md">
              {saved.source}
            </Text>
          )}
          {!readOnly && (
            <Text size="xs" c={dirty ? 'orange.8' : 'dimmed'} className="nowrap" data-testid="save-state">
              {save.isPending ? 'Saving…' : dirty ? 'Unsaved changes' : 'Saved'}
            </Text>
          )}
        </Group>
        <Group gap={6} wrap="nowrap">
          {!readOnly && problemCount > 0 && (
            <Badge size="sm" color="red" variant="light" tt="none">
              {problemCount} problem{problemCount === 1 ? '' : 's'}
            </Badge>
          )}
          {flagged > 0 && (
            <Badge size="sm" color="orange" variant="light" tt="none">
              {flagged} flagged
            </Badge>
          )}
          {!readOnly && (
            <>
              <Button size="xs" variant="default" disabled={!dirty || busy} loading={save.isPending} onClick={() => save.mutate()}>
                Save
              </Button>
              <Button size="xs" disabled={busy || problemCount > 0 || validation.isFetching} loading={publish.isPending} onClick={() => publish.mutate()} title={problemCount ? 'Fix the problems first' : undefined}>
                Publish
              </Button>
              <Button size="xs" variant="subtle" color="red" disabled={busy} onClick={() => setConfirmDiscard(true)}>
                Discard draft
              </Button>
            </>
          )}
        </Group>
      </Paper>

      {!canEditTemplates && (
        <Alert color="gray" p="xs" mt={6}>
          <Text size="xs">Read-only: your role can’t edit templates.</Text>
        </Alert>
      )}
      {canEditTemplates && saved.status !== 'draft' && (
        <Alert color="gray" p="xs" mt={6}>
          <Text size="xs">
            A {saved.status} version can’t be edited. Start a new draft from the{' '}
            <Anchor component={Link} to="/templates" size="xs">
              templates list
            </Anchor>
            .
          </Text>
        </Alert>
      )}
      {notice && (
        <Alert color={notice.color} p="xs" mt={6} withCloseButton onClose={() => setNotice(null)} role="status">
          <Text size="xs">{notice.text}</Text>
        </Alert>
      )}
      {problems.template.length > 0 && (
        <Alert color="red" p="xs" mt={6}>
          <List size="xs">
            {problems.template.map((m) => (
              <List.Item key={m}>{m}</List.Item>
            ))}
          </List>
        </Alert>
      )}

      <div className="editor-columns">
        <section className="editor-main">
          <Title order={6} mt={8} mb={4}>
            Inputs
          </Title>
          <ParamsTable
            params={draft.parameters}
            problems={problems.params}
            uoms={(uoms.data ?? []).map((u) => u.code)}
            readOnly={readOnly}
            onChange={(parameters) => change((d) => ({ ...d, parameters }))}
          />
          <Title order={6} mt={12} mb={4}>
            Lines
          </Title>
          <LinesTable
            lines={draft.lines}
            problems={problems.lines}
            paramNames={paramNames}
            costHeads={costHeads.data ?? []}
            readOnly={readOnly}
            onChange={(lines) => change((d) => ({ ...d, lines }))}
          />
          <Textarea
            mt={8}
            size="xs"
            label="Notes for this version"
            autosize
            minRows={1}
            value={draft.notes ?? ''}
            disabled={readOnly}
            onChange={(e) => {
              const notes = e.currentTarget.value || null
              change((d) => ({ ...d, notes }))
            }}
          />
        </section>
        {canEditTemplates && (
          <aside className="editor-preview">
            <TemplatePreview template={saved} revision={revision} unsavedChanges={dirty} />
          </aside>
        )}
      </div>

      <Modal opened={confirmDiscard} onClose={() => setConfirmDiscard(false)} title="Discard this draft?" size="sm">
        <Text size="sm" mb="md">
          v{saved.version} of {saved.sign_type_name} will be deleted. The published version is not affected.
        </Text>
        <Group justify="flex-end">
          <Button size="xs" variant="default" onClick={() => setConfirmDiscard(false)}>
            Keep it
          </Button>
          <Button size="xs" color="red" loading={discard.isPending} onClick={() => discard.mutate()}>
            Discard
          </Button>
        </Group>
      </Modal>
    </div>
  )
}
