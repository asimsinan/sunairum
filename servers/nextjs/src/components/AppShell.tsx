'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Figtree, Sora } from 'next/font/google'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { UIProvider, useUI } from '@/lib/i18n'
import { AuthProvider, isAuthRoute, useAuth } from '@/lib/auth'
import { apiFetch, apiJson } from '@/lib/api'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import ThemeToggle from '@/components/ThemeToggle'
import SidebarNav from '@/components/SidebarNav'
import Icon from '@/components/Icon'
import FeedbackHost from '@/components/feedback/FeedbackHost'
import styles from './app-shell.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'], variable: '--font-sora' })
const figtree = Figtree({
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
  variable: '--font-figtree',
})

const IDLE_WARN_MS = 60_000
const ACTIVITY_THROTTLE_MS = 1_000
const TOUCH_THROTTLE_MS = 30_000

function IdleWarningModal({
  secondsLeft,
  onStay,
  onLogout,
}: {
  secondsLeft: number
  onStay: () => void
  onLogout: () => void
}) {
  const { t } = useUI()
  return (
    <div className={styles.idleOverlay} role="presentation">
      <div className={styles.idleModal} role="alertdialog" aria-modal="true" aria-labelledby="idle-title">
        <h2 id="idle-title" className={styles.idleTitle}>
          {t('idleTitle')}
        </h2>
        <p className={styles.idleMessage}>{t('idleMessage')}</p>
        <p className={styles.idleCountdown}>{t('idleSeconds', { n: Math.max(0, secondsLeft) })}</p>
        <div className={styles.idleActions}>
          <button type="button" className={styles.idleGhost} onClick={onLogout}>
            {t('idleLogout')}
          </button>
          <button type="button" className={styles.idlePrimary} onClick={onStay}>
            {t('idleStay')}
          </button>
        </div>
      </div>
    </div>
  )
}

function UserMenu({ collapsed }: { collapsed: boolean }) {
  const { t } = useUI()
  const { user, logout } = useAuth()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!user) return null

  const label = user.display_name || user.email

  return (
    <div className={styles.userMenu} ref={ref}>
      <button
        type="button"
        className={styles.userMenuButton}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('userMenu')}
        onClick={() => setOpen((v) => !v)}
        title={label}
      >
        <span className={styles.userAvatar} aria-hidden>
          {(label[0] || '?').toUpperCase()}
        </span>
        {!collapsed && (
          <span className={styles.userMeta}>
            <span className={styles.userName}>{label}</span>
            <span className={styles.userEmail}>{user.email}</span>
          </span>
        )}
      </button>
      {open && (
        <div className={styles.userDropdown} role="menu">
          <Link
            href="/profile"
            role="menuitem"
            className={styles.userDropdownItem}
            onClick={() => setOpen(false)}
          >
            <Icon name="user" className={styles.userDropdownIcon} />
            {t('navProfile')}
          </Link>
          <div className={styles.userDropdownDivider} role="separator" />
          <button
            type="button"
            role="menuitem"
            className={`${styles.userDropdownItem} ${styles.userDropdownDanger}`}
            onClick={async () => {
              setOpen(false)
              await logout()
              router.replace('/login')
            }}
          >
            <Icon name="logOut" className={styles.userDropdownIcon} />
            {t('logout')}
          </button>
        </div>
      )}
    </div>
  )
}

function ShellContent({ children }: { children: React.ReactNode }) {
  const { t } = useUI()
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, logout, updateUser, refreshMe } = useAuth()
  const isDeckEditor = /^\/editor\/[^/]+\/deck\/?$/.test(pathname || '')
  const authPage = isAuthRoute(pathname)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [idleWarn, setIdleWarn] = useState(false)
  const [idleSeconds, setIdleSeconds] = useState(0)
  const idleExpiresRef = useRef<number | null>(null)
  const lastThrottleRef = useRef(0)
  const lastTouchRef = useRef(0)
  const idleLoggedOutRef = useRef(false)
  const staySignedInRef = useRef<() => Promise<boolean>>(async () => false)

  useEffect(() => {
    setCollapsed(localStorage.getItem('sunairum_sidebar') === 'collapsed')
  }, [])

  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  useEffect(() => {
    if (!mobileOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [mobileOpen])

  // Route guards
  useEffect(() => {
    if (loading) return
    if (!user) {
      if (!authPage) router.replace('/login')
      return
    }
    if (user.status === 'pending' && pathname !== '/pending') {
      router.replace('/pending')
      return
    }
    if (user.status === 'rejected' && pathname !== '/rejected') {
      router.replace('/rejected')
      return
    }
    if (user.status === 'approved' && (pathname === '/login' || pathname === '/signup')) {
      router.replace('/')
    }
  }, [loading, user, authPage, pathname, router])

  // Pending badge for admins
  useEffect(() => {
    if (!user || user.role !== 'admin' || user.status !== 'approved') {
      setPendingCount(0)
      return
    }
    let cancelled = false
    const load = async () => {
      try {
        const stats = await apiJson<{ pending: number }>('/api/admin/stats')
        if (!cancelled) setPendingCount(stats.pending || 0)
      } catch {
        if (!cancelled) setPendingCount(0)
      }
    }
    void load()
    const id = setInterval(load, 60_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [user])

  // Sync idle expiry from user payload
  useEffect(() => {
    idleExpiresRef.current =
      user?.status === 'approved' && typeof user.idle_expires_at === 'number'
        ? user.idle_expires_at
        : null
    idleLoggedOutRef.current = false
  }, [user?.idle_expires_at, user?.status])

  const forceIdleLogout = useCallback(async () => {
    if (idleLoggedOutRef.current) return
    idleLoggedOutRef.current = true
    setIdleWarn(false)
    try {
      await apiFetch('/api/auth/logout', { method: 'POST', skipAuthRedirect: true })
    } catch {
      /* ignore */
    }
    await logout()
    router.replace('/login?reason=idle')
  }, [logout, router])

  const touchSession = useCallback(
    async ({ logoutOnFail }: { logoutOnFail: boolean }) => {
      try {
        const data = await apiJson<{
          ok: boolean
          idle_expires_at?: number
          absolute_expires_at?: number
        }>('/api/auth/session/touch', { method: 'POST' })
        lastTouchRef.current = Date.now()
        if (typeof data.idle_expires_at === 'number') {
          idleExpiresRef.current = data.idle_expires_at
          updateUser({
            idle_expires_at: data.idle_expires_at,
            absolute_expires_at: data.absolute_expires_at,
          })
        } else {
          await refreshMe()
        }
        setIdleWarn(false)
        return true
      } catch {
        if (logoutOnFail) await forceIdleLogout()
        return false
      }
    },
    [forceIdleLogout, refreshMe, updateUser],
  )

  const staySignedIn = useCallback(() => touchSession({ logoutOnFail: true }), [touchSession])

  staySignedInRef.current = () => touchSession({ logoutOnFail: false })

  // Activity + idle countdown for approved users
  useEffect(() => {
    if (!user || user.status !== 'approved') {
      setIdleWarn(false)
      return
    }

    const onActivity = () => {
      const now = Date.now()
      if (now - lastThrottleRef.current < ACTIVITY_THROTTLE_MS) return
      lastThrottleRef.current = now
      if (now - lastTouchRef.current >= TOUCH_THROTTLE_MS) {
        lastTouchRef.current = now
        void staySignedInRef.current()
      }
    }

    const events: Array<keyof WindowEventMap> = [
      'mousemove',
      'keydown',
      'click',
      'scroll',
      'touchstart',
    ]
    events.forEach((name) => window.addEventListener(name, onActivity, { passive: true }))

    const tick = () => {
      const expires = idleExpiresRef.current
      if (!expires) return
      const msLeft = expires * 1000 - Date.now()
      if (msLeft <= 0) {
        void forceIdleLogout()
        return
      }
      if (msLeft <= IDLE_WARN_MS) {
        setIdleWarn(true)
        setIdleSeconds(Math.ceil(msLeft / 1000))
      } else {
        setIdleWarn(false)
      }
    }

    tick()
    const id = setInterval(tick, 1000)
    return () => {
      clearInterval(id)
      events.forEach((name) => window.removeEventListener(name, onActivity))
    }
  }, [user, forceIdleLogout])

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      const next = !value
      localStorage.setItem('sunairum_sidebar', next ? 'collapsed' : 'expanded')
      return next
    })
  }

  const shellClass = `${styles.shell} ${sora.variable} ${figtree.variable} ${figtree.className}`

  if (loading) {
    return (
      <div className={shellClass}>
        <main className={styles.authMain} aria-busy="true" />
        <FeedbackHost />
      </div>
    )
  }

  if (isDeckEditor) {
    return (
      <div className={shellClass} data-deck-editor="true">
        <main className={styles.main} style={{ margin: 0, padding: 0, maxWidth: 'none' }}>
          {children}
        </main>
        <FeedbackHost />
        {idleWarn && (
          <IdleWarningModal secondsLeft={idleSeconds} onStay={() => void staySignedIn()} onLogout={() => void forceIdleLogout()} />
        )}
      </div>
    )
  }

  if (authPage) {
    return (
      <div className={shellClass}>
        <main className={styles.authMain}>{children}</main>
        <FeedbackHost />
      </div>
    )
  }

  // Gate non-approved sessions away from the app chrome (pending/rejected use auth shell).
  if (!user || user.status !== 'approved') {
    if (pathname === '/pending' || pathname === '/rejected') {
      return (
        <div className={shellClass}>
          <main className={styles.authMain}>{children}</main>
          <FeedbackHost />
        </div>
      )
    }
    return (
      <div className={shellClass}>
        <main className={styles.authMain} />
        <FeedbackHost />
      </div>
    )
  }

  return (
    <div className={`${shellClass} ${collapsed ? styles.shellCollapsed : ''}`}>
      <button
        type="button"
        className={styles.mobileMenu}
        onClick={() => setMobileOpen(true)}
        aria-label={t('openNavigation')}
      >
        <Icon name="menu" className="w-5 h-5" />
      </button>
      {mobileOpen && (
        <button className={styles.scrim} onClick={() => setMobileOpen(false)} aria-label={t('closeNavigation')} />
      )}
      <aside className={`${styles.sidebar} ${mobileOpen ? styles.sidebarMobileOpen : ''}`}>
        <div className={styles.brandRow}>
          <img
            src="/logo.png?v=transparent"
            alt="Sunairum"
            className={styles.brandMark}
            width={36}
            height={36}
            decoding="async"
          />
          <span className={styles.brandName}>Sunairum</span>
          <button
            type="button"
            className={styles.collapseButton}
            onClick={toggleCollapsed}
            aria-label={collapsed ? t('expandNavigation') : t('collapseNavigation')}
            title={collapsed ? t('expandNavigation') : t('collapseNavigation')}
          >
            <Icon name={collapsed ? 'arrowRight' : 'arrowLeft'} className="w-4 h-4" />
          </button>
        </div>
        <nav className={styles.nav} aria-label={t('navHome')}>
          <SidebarNav collapsed={collapsed && !mobileOpen} pendingCount={pendingCount} />
        </nav>
        <div className={styles.sidebarFooter}>
          <UserMenu collapsed={collapsed && !mobileOpen} />
          <div className={styles.footerTools}>
            <ThemeToggle />
            <LanguageSwitcher />
          </div>
        </div>
      </aside>
      <main className={styles.main}>{children}</main>
      <FeedbackHost />
      {idleWarn && (
        <IdleWarningModal
          secondsLeft={idleSeconds}
          onStay={() => void staySignedIn()}
          onLogout={() => void forceIdleLogout()}
        />
      )}
    </div>
  )
}

export default function AppShell({
  children,
  initialLang,
}: {
  children: React.ReactNode
  initialLang: 'tr' | 'en'
}) {
  return (
    <UIProvider initialLang={initialLang}>
      <AuthProvider>
        <ShellContent>{children}</ShellContent>
      </AuthProvider>
    </UIProvider>
  )
}
