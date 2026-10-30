import { Anchor, Badge, Button, Group, Text } from '@mantine/core'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

const NAV = [
  { to: '/', label: 'Orders', end: true },
  { to: '/templates', label: 'Templates', end: false },
]

export function AppLayout() {
  const { user, logout } = useAuth()
  return (
    <>
      <header className="app-header">
        <Group justify="space-between" gap="xs">
          <Group gap="lg" wrap="nowrap">
            <Text fw={700}>BOM System</Text>
            <nav className="app-nav">
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  {n.label}
                </NavLink>
              ))}
            </nav>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Text size="sm" truncate visibleFrom="xs">
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
      <footer className="app-footer">
        <Text size="xs" c="dimmed">
          MVP v1.0 by AH & SA
        </Text>
      </footer>
    </>
  )
}

export { Anchor }
