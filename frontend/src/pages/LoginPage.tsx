import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { type FormEvent, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { errorMessage, safeNext } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

export function LoginPage() {
  const { user, login } = useAuth()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={safeNext(searchParams.get('next'))} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center h="100vh" p="md">
      <Paper withBorder p="xl" w="100%" maw={360}>
        <form onSubmit={submit}>
          <Stack>
            <Title order={3}>BOM System</Title>
            {error && (
              <Alert color="red" role="alert">
                {error}
              </Alert>
            )}
            <TextInput
              label="Email"
              type="email"
              autoComplete="username"
              autoFocus
              required
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
            />
            <PasswordInput
              label="Password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
            />
            <Button type="submit" loading={busy}>
              Sign in
            </Button>
            <Text size="xs" c="dimmed" ta="center">
              MVP v1.0 by Ali H. & Saad A.
            </Text>
          </Stack>
        </form>
      </Paper>
    </Center>
  )
}
