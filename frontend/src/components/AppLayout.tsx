import { Anchor, Badge, Button, Group, Text } from '@mantine/core'
import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

export function AppLayout() {
  const { user, logout } = useAuth()
  return (
    <>
      <header className="app-header">
        <Group justify="space-between" wrap="nowrap">
          <Anchor component={Link} to="/" fw={700} c="dark" underline="never">
            BOM System
          </Anchor>
          <Group gap="xs" wrap="nowrap">
            <Text size="sm" truncate>
              {user?.name}
            </Text>
            <Badge variant="light" color="gray" size="sm">
              {user?.role.replace('_', ' ')}
            </Badge>
            <Button variant="subtle" size="compact-sm" onClick={logout}>
              Sign out
            </Button>
          </Group>
        </Group>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </>
  )
}
