import { AppShell, Burger, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { ordersQuery } from '../lib/orders'

const ICONS = {
  orders: <path d="M4 6h16M4 12h16M4 18h10" />,
  templates: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M9 10v10" />
    </>
  ),
  inventory: <path d="M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8" />,
  sync: <path d="M21 12a9 9 0 0 1-15.5 6.2M3 12a9 9 0 0 1 15.5-6.2M3 4v5h5M21 20v-5h-5" />,
  reports: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
}

const NAV: { to: string; label: string; icon: keyof typeof ICONS; match: (path: string) => boolean }[] = [
  { to: '/', label: 'Orders', icon: 'orders', match: (p) => p === '/' || p.startsWith('/orders') || p.startsWith('/boms') },
  { to: '/templates', label: 'Templates', icon: 'templates', match: (p) => p.startsWith('/templates') || p.startsWith('/sign-types') },
  { to: '/inventory', label: 'Inventory', icon: 'inventory', match: (p) => p.startsWith('/inventory') },
  { to: '/sync', label: 'Airtable sync', icon: 'sync', match: (p) => p.startsWith('/sync') },
  { to: '/reports', label: 'Reports', icon: 'reports', match: (p) => p.startsWith('/reports') },
]

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  template_owner: 'Template owner',
  bom_editor: 'BOM editor',
  inventory_manager: 'Inventory manager',
  viewer: 'Viewer',
}

const initials = (name: string | undefined) =>
  (name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join('')

export function AppLayout() {
  const { user, logout } = useAuth()
  const [opened, { toggle, close }] = useDisclosure(false)
  const location = useLocation()
  const needsBom = useQuery(ordersQuery('needs_bom')).data?.length

  return (
    <AppShell navbar={{ width: 256, breakpoint: 'sm', collapsed: { mobile: !opened } }} padding={0} withBorder={false}>
      <AppShell.Navbar className="sidebar" aria-label="Main">
        <div className="sidebar-brand">
          <div className="logo-mark" aria-hidden="true">
            B
          </div>
          <div>
            <div className="wordmark">BOM System</div>
            <div className="caption">Epic Crafting</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV.map((n) => {
            const active = n.match(location.pathname)
            return (
              <NavLink key={n.to} to={n.to} className={active ? 'active' : undefined} aria-current={active ? 'page' : undefined} onClick={close}>
                <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {ICONS[n.icon]}
                </svg>
                {n.label}
                {n.icon === 'orders' && !!needsBom && (
                  <span className="nav-count" title={`${needsBom} orders need a BOM`}>
                    {needsBom}
                  </span>
                )}
              </NavLink>
            )
          })}
        </nav>
        <div className="sidebar-user">
          <div className="avatar" aria-hidden="true">
            {initials(user?.name)}
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="body-strong" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.name}
            </div>
            <div className="caption">{user ? (ROLE_LABEL[user.role] ?? user.role) : ''}</div>
          </div>
          <button type="button" className="link-button sidebar-signout" onClick={logout}>
            Sign out
          </button>
        </div>
        <div className="caption sidebar-footer">MVP v1.0 by Ali H. &amp; Saad A.</div>
      </AppShell.Navbar>
      <AppShell.Main className="app-main">
        <div className="phone-bar" hidden={false}>
          <Burger opened={opened} onClick={toggle} aria-label="Menu" size="sm" hiddenFrom="sm" />
          <Text className="wordmark" hiddenFrom="sm">
            BOM System
          </Text>
        </div>
        <main className="sheet">
          <Outlet />
        </main>
      </AppShell.Main>
    </AppShell>
  )
}
