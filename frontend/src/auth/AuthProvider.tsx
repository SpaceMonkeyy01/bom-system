import { Alert, Button, Center, Loader, Stack } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { api, clearToken, errorMessage, getToken, setToken } from '../api/client'
import type { Role, TokenOut, User } from '../api/types'

// Mirrors PERMISSIONS["bom:write"] in backend/app/services/auth.py. The API enforces it; this only hides buttons.
const BOM_WRITE_ROLES: Role[] = ['admin', 'template_owner', 'bom_editor']

export const canWriteBom = (role: Role | undefined) => !!role && BOM_WRITE_ROLES.includes(role)

interface AuthValue {
  user: User | undefined
  canWrite: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

const fetchMe = () => api<User>('/auth/me')

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [hasToken, setHasToken] = useState(() => !!getToken())
  const me = useQuery({ queryKey: ['me'], queryFn: fetchMe, enabled: hasToken, staleTime: Infinity })

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api<TokenOut>('/auth/login', {
        form: { username: email, password },
        skipAuthRedirect: true,
      })
      setToken(res.access_token)
      queryClient.setQueryData(['me'], await fetchMe())
      setHasToken(true)
    },
    [queryClient],
  )

  const logout = useCallback(() => {
    clearToken()
    setHasToken(false)
    queryClient.clear()
  }, [queryClient])

  const value = useMemo<AuthValue>(
    () => ({ user: hasToken ? me.data : undefined, canWrite: canWriteBom(me.data?.role), login, logout }),
    [hasToken, me.data, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

/** Route guard: no token -> /login; otherwise wait for /auth/me before rendering the page. */
export function RequireAuth() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const me = useQuery({ queryKey: ['me'], queryFn: fetchMe, enabled: !!getToken(), staleTime: Infinity })

  if (!getToken()) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  }
  if (user) return <Outlet />
  if (me.isError) {
    return (
      <Center h="100vh">
        <Stack>
          <Alert color="red" title="Couldn’t load your account">
            {errorMessage(me.error)}
          </Alert>
          <Button variant="default" onClick={() => me.refetch()}>
            Try again
          </Button>
          <Button variant="subtle" onClick={logout}>
            Sign out
          </Button>
        </Stack>
      </Center>
    )
  }
  return (
    <Center h="100vh">
      <Loader />
    </Center>
  )
}
