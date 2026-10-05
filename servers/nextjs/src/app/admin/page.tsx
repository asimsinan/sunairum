'use client'

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Figtree, Sora } from 'next/font/google'
import { apiFetch, apiJson } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useUI } from '@/lib/i18n'
import { notify } from '@/components/feedback/notify'
import styles from './admin.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700'] })

type AdminUser = {
  id: string
  email: string
  display_name: string
  role: string
  status: string
  created_at?: number
  last_login_at?: number | null
  active_sessions?: number
}

type Stats = {
  pending: number
  approved: number
  rejected: number
  disabled: number
  total: number
}

type StatusFilter = 'all' | 'pending' | 'approved' | 'rejected' | 'disabled'

function detailOf(data: unknown, fallback: string) {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === 'string') return d
  }
  return fallback
}

export default function AdminPage() {
  const { t, lang } = useUI()
  const { user: me } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null)
  const [createForm, setCreateForm] = useState({
    email: '',
    password: '',
    display_name: '',
    role: 'user',
    status: 'approved',
  })
  const [resetPassword, setResetPassword] = useState('')
  const locale = lang === 'en' ? 'en-US' : 'tr-TR'

  const load = useCallback(async () => {
    try {
      const statusQuery = filter === 'all' ? '' : `?status=${filter}`
      const [usersData, statsData] = await Promise.all([
        apiJson<{ users: AdminUser[] }>(`/api/admin/users${statusQuery}`),
        apiJson<Stats>('/api/admin/stats'),
      ])
      setUsers(usersData.users || [])
      setStats(statsData)
    } catch (err) {
      console.error(err)
      notify.toast({ title: t('adminLoadFailed'), message: t('adminLoadFailed'), tone: 'error' })
    } finally {
      setLoading(false)
    }
  }, [filter, t])

  useEffect(() => {
    setLoading(true)
    void load()
  }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return users
    return users.filter(
      (u) =>
        u.email.toLowerCase().includes(q) ||
        (u.display_name || '').toLowerCase().includes(q),
    )
  }, [users, search])

  const toastError = (message: string) =>
    notify.toast({ title: t('adminActionFailed'), message, tone: 'error' })

  const runAction = async (path: string, init?: RequestInit) => {
    const res = await apiFetch(path, init)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(detailOf(data, t('adminActionFailed')))
    await load()
  }

  const onApprove = (id: string) =>
    runAction(`/api/admin/users/${id}/approve`, { method: 'POST' }).catch((e) =>
      toastError(e.message),
    )
  const onReject = (id: string) =>
    runAction(`/api/admin/users/${id}/reject`, { method: 'POST' }).catch((e) =>
      toastError(e.message),
    )
  const onDisable = (id: string) =>
    runAction(`/api/admin/users/${id}/disable`, { method: 'POST' }).catch((e) =>
      toastError(e.message),
    )
  const onEnable = (id: string) =>
    runAction(`/api/admin/users/${id}/enable`, { method: 'POST' }).catch((e) =>
      toastError(e.message),
    )

  const onRemove = async (u: AdminUser) => {
    const ok = await notify.confirm({
      title: t('adminRemoveConfirmTitle'),
      message: t('adminRemoveConfirm', { email: u.email }),
      confirmLabel: t('adminRemove'),
      tone: 'danger',
    })
    if (!ok) return
    try {
      await runAction(`/api/admin/users/${u.id}`, { method: 'DELETE' })
      notify.toast({
        title: t('adminRemoved'),
        message: t('adminRemoved'),
        tone: 'success',
        durationMs: 1500,
      })
    } catch (e) {
      toastError(e instanceof Error ? e.message : t('adminActionFailed'))
    }
  }

  const onRemoveAll = async () => {
    const ok = await notify.confirm({
      title: t('adminRemoveAllConfirmTitle'),
      message: t('adminRemoveAllConfirm'),
      confirmLabel: t('adminRemoveAll'),
      tone: 'danger',
    })
    if (!ok) return
    try {
      await runAction('/api/admin/users', {
        method: 'DELETE',
        body: JSON.stringify({ confirm: 'DELETE_ALL' }),
      })
      notify.toast({
        title: t('adminRemovedAll'),
        message: t('adminRemovedAll'),
        tone: 'success',
        durationMs: 1500,
      })
    } catch (e) {
      toastError(e instanceof Error ? e.message : t('adminActionFailed'))
    }
  }

  const onRoleChange = async (id: string, role: string) => {
    try {
      await runAction(`/api/admin/users/${id}/role`, {
        method: 'PATCH',
        body: JSON.stringify({ role }),
      })
    } catch (e) {
      toastError(e instanceof Error ? e.message : t('adminActionFailed'))
    }
  }

  const onCreate = async (event: FormEvent) => {
    event.preventDefault()
    try {
      await runAction('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify(createForm),
      })
      setCreateOpen(false)
      setCreateForm({
        email: '',
        password: '',
        display_name: '',
        role: 'user',
        status: 'approved',
      })
      notify.toast({
        title: t('adminUserCreated'),
        message: t('adminUserCreated'),
        tone: 'success',
        durationMs: 1500,
      })
    } catch (e) {
      toastError(e instanceof Error ? e.message : t('adminActionFailed'))
    }
  }

  const onReset = async (event: FormEvent) => {
    event.preventDefault()
    if (!resetTarget) return
    try {
      await runAction(`/api/admin/users/${resetTarget.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password: resetPassword }),
      })
      setResetTarget(null)
      setResetPassword('')
      notify.toast({
        title: t('adminPasswordReset'),
        message: t('adminPasswordReset'),
        tone: 'success',
        durationMs: 1500,
      })
    } catch (e) {
      toastError(e instanceof Error ? e.message : t('adminActionFailed'))
    }
  }

  const formatDate = (ts?: number | null) => {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleString(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  }

  const statusBadge = (status: string) => {
    const map: Record<string, string> = {
      pending: styles.badgePending,
      approved: styles.badgeApproved,
      rejected: styles.badgeRejected,
      disabled: styles.badgeDisabled,
    }
    return `${styles.badge} ${map[status] || styles.badgeDisabled}`
  }

  const statusLabel = (status: string) => {
    const map: Record<string, string> = {
      pending: 'adminStatusPending',
      approved: 'adminStatusApproved',
      rejected: 'adminStatusRejected',
      disabled: 'adminStatusDisabled',
    }
    return t(map[status] || status)
  }

  if (me && me.role !== 'admin') {
    return (
      <div className={`${styles.page} ${sora.className} ${figtree.className}`}>
        <p className={styles.empty}>{t('adminForbidden')}</p>
      </div>
    )
  }

  return (
    <div className={`${styles.page} ${sora.className} ${figtree.className}`}>
      <header className={styles.hero}>
        <div className={styles.eyebrow}>
          <span className={styles.eyebrowMark} />
          {t('adminEyebrow')}
        </div>
        <h1 className={styles.title}>{t('adminTitle')}</h1>
        <p className={styles.subtitle}>{t('adminSubtitle')}</p>
      </header>

      {stats && (
        <div className={styles.stats}>
          <div className={styles.stat}>
            <div className={styles.statLabel}>{t('adminPending')}</div>
            <div className={styles.statValue}>{stats.pending}</div>
          </div>
          <div className={styles.stat}>
            <div className={styles.statLabel}>{t('adminApproved')}</div>
            <div className={styles.statValue}>{stats.approved}</div>
          </div>
          <div className={styles.stat}>
            <div className={styles.statLabel}>{t('adminRejected')}</div>
            <div className={styles.statValue}>{stats.rejected}</div>
          </div>
          <div className={styles.stat}>
            <div className={styles.statLabel}>{t('adminDisabled')}</div>
            <div className={styles.statValue}>{stats.disabled}</div>
          </div>
          <div className={styles.stat}>
            <div className={styles.statLabel}>{t('adminTotal')}</div>
            <div className={styles.statValue}>{stats.total}</div>
          </div>
        </div>
      )}

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="search"
          placeholder={t('adminSearch')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className={styles.filters}>
          {(['all', 'pending', 'approved', 'rejected', 'disabled'] as StatusFilter[]).map((id) => (
            <button
              key={id}
              type="button"
              className={styles.filterBtn}
              data-active={filter === id}
              onClick={() => setFilter(id)}
            >
              {t(
                id === 'all'
                  ? 'adminFilterAll'
                  : id === 'pending'
                    ? 'adminStatusPending'
                    : id === 'approved'
                      ? 'adminStatusApproved'
                      : id === 'rejected'
                        ? 'adminStatusRejected'
                        : 'adminStatusDisabled',
              )}
            </button>
          ))}
        </div>
        <button type="button" className={styles.createBtn} onClick={() => setCreateOpen(true)}>
          {t('adminCreateUser')}
        </button>
        <button
          type="button"
          className={styles.dangerBtn}
          onClick={() => void onRemoveAll()}
          disabled={users.filter((u) => u.id !== me?.id).length === 0}
        >
          {t('adminRemoveAll')}
        </button>
      </div>

      <div className={styles.panel}>
        {loading ? (
          <p className={styles.empty}>{t('loading')}</p>
        ) : filtered.length === 0 ? (
          <p className={styles.empty}>{t('adminNoUsers')}</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t('adminUsers')}</th>
                  <th>{t('adminStatus')}</th>
                  <th>{t('adminRole')}</th>
                  <th>{t('adminLastLogin')}</th>
                  <th>{t('adminActions')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div className={styles.userCell}>
                        <span className={styles.userName}>{u.display_name || u.email}</span>
                        <span className={styles.userEmail}>{u.email}</span>
                      </div>
                    </td>
                    <td>
                      <span className={statusBadge(u.status)}>{statusLabel(u.status)}</span>
                    </td>
                    <td>
                      <select
                        className={styles.select}
                        value={u.role}
                        onChange={(e) => void onRoleChange(u.id, e.target.value)}
                        disabled={u.id === me?.id}
                      >
                        <option value="user">{t('adminRoleUser')}</option>
                        <option value="admin">{t('adminRoleAdmin')}</option>
                      </select>
                    </td>
                    <td>{formatDate(u.last_login_at)}</td>
                    <td>
                      <div className={styles.actions}>
                        {u.status === 'pending' && (
                          <>
                            <button
                              type="button"
                              className={`${styles.actionBtn} ${styles.actionSuccess}`}
                              onClick={() => void onApprove(u.id)}
                            >
                              {t('adminApprove')}
                            </button>
                            <button
                              type="button"
                              className={`${styles.actionBtn} ${styles.actionDanger}`}
                              onClick={() => void onReject(u.id)}
                            >
                              {t('adminReject')}
                            </button>
                          </>
                        )}
                        {u.status === 'approved' && (
                          <button
                            type="button"
                            className={`${styles.actionBtn} ${styles.actionWarn}`}
                            onClick={() => void onDisable(u.id)}
                          >
                            {t('adminDisable')}
                          </button>
                        )}
                        {(u.status === 'disabled' || u.status === 'rejected') && (
                          <button
                            type="button"
                            className={`${styles.actionBtn} ${styles.actionSuccess}`}
                            onClick={() => void onEnable(u.id)}
                          >
                            {t('adminEnable')}
                          </button>
                        )}
                        <button
                          type="button"
                          className={`${styles.actionBtn} ${styles.actionAccent}`}
                          onClick={() => {
                            setResetTarget(u)
                            setResetPassword('')
                          }}
                        >
                          {t('adminResetPassword')}
                        </button>
                        {u.id !== me?.id && (
                          <button
                            type="button"
                            className={`${styles.actionBtn} ${styles.actionDanger}`}
                            onClick={() => void onRemove(u)}
                          >
                            {t('adminRemove')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {createOpen && (
        <div className={styles.modalOverlay} role="presentation" onClick={() => setCreateOpen(false)}>
          <div
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-create-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="admin-create-title" className={styles.modalTitle}>
              {t('adminCreateUser')}
            </h2>
            <p className={styles.modalDesc}>{t('adminCreateDesc')}</p>
            <form onSubmit={onCreate}>
              <label className={styles.field}>
                <span className={styles.label}>{t('adminCreateName')}</span>
                <input
                  className={styles.input}
                  value={createForm.display_name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, display_name: e.target.value }))}
                />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>{t('adminCreateEmail')}</span>
                <input
                  className={styles.input}
                  type="email"
                  required
                  value={createForm.email}
                  onChange={(e) => setCreateForm((f) => ({ ...f, email: e.target.value }))}
                />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>{t('adminCreatePassword')}</span>
                <input
                  className={styles.input}
                  type="password"
                  required
                  minLength={8}
                  value={createForm.password}
                  onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
                />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>{t('adminRole')}</span>
                <select
                  className={styles.input}
                  value={createForm.role}
                  onChange={(e) => setCreateForm((f) => ({ ...f, role: e.target.value }))}
                >
                  <option value="user">{t('adminRoleUser')}</option>
                  <option value="admin">{t('adminRoleAdmin')}</option>
                </select>
              </label>
              <div className={styles.modalActions}>
                <button type="button" className={styles.btnSecondary} onClick={() => setCreateOpen(false)}>
                  {t('cancel')}
                </button>
                <button type="submit" className={styles.btnPrimary}>
                  {t('adminCreate')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {resetTarget && (
        <div className={styles.modalOverlay} role="presentation" onClick={() => setResetTarget(null)}>
          <div
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className={styles.modalTitle}>{t('adminResetPassword')}</h2>
            <p className={styles.modalDesc}>
              {t('adminResetDesc', { email: resetTarget.email })}
            </p>
            <form onSubmit={onReset}>
              <label className={styles.field}>
                <span className={styles.label}>{t('adminCreatePassword')}</span>
                <input
                  className={styles.input}
                  type="password"
                  required
                  minLength={8}
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                />
              </label>
              <div className={styles.modalActions}>
                <button type="button" className={styles.btnSecondary} onClick={() => setResetTarget(null)}>
                  {t('cancel')}
                </button>
                <button type="submit" className={styles.btnPrimary}>
                  {t('adminResetPassword')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
