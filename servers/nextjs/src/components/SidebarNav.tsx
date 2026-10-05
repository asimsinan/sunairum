'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useUI } from '@/lib/i18n'
import { useAuth } from '@/lib/auth'
import Icon from './Icon'
import styles from './app-shell.module.css'

const NAV_ITEMS = [
  { href: '/', icon: 'home', labelKey: 'navHome' },
  { href: '/history', icon: 'history', labelKey: 'navHistory' },
  { href: '/settings', icon: 'settings', labelKey: 'navSettings' },
] as const

function isActive(pathname: string, href: string) {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}

export default function SidebarNav({
  collapsed = false,
  pendingCount = 0,
}: {
  collapsed?: boolean
  pendingCount?: number
}) {
  const { t } = useUI()
  const { user } = useAuth()
  const pathname = usePathname() || '/'
  const isAdmin = user?.role === 'admin'

  return (
    <>
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href)
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`${styles.navLink}${active ? ` ${styles.navLinkActive}` : ''}`}
            aria-current={active ? 'page' : undefined}
          >
            <Icon name={item.icon} className="w-5 h-5 shrink-0" />
            <span className={`${styles.navLabel}${collapsed ? ` ${styles.navLabelHidden}` : ''}`}>
              {t(item.labelKey)}
            </span>
          </Link>
        )
      })}
      {isAdmin && (
        <Link
          href="/admin"
          className={`${styles.navLink}${isActive(pathname, '/admin') ? ` ${styles.navLinkActive}` : ''}`}
          aria-current={isActive(pathname, '/admin') ? 'page' : undefined}
        >
          <Icon name="users" className="w-5 h-5 shrink-0" />
          <span className={`${styles.navLabel}${collapsed ? ` ${styles.navLabelHidden}` : ''}`}>
            {t('navAdmin')}
          </span>
          {pendingCount > 0 && (
            <span className={styles.navBadge} aria-label={`${pendingCount}`}>
              {pendingCount > 99 ? '99+' : pendingCount}
            </span>
          )}
        </Link>
      )}
    </>
  )
}
