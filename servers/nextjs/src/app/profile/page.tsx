'use client'

import { FormEvent, useEffect, useState } from 'react'
import { Figtree, Sora } from 'next/font/google'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/api'
import { useUI } from '@/lib/i18n'
import { notify } from '@/components/feedback/notify'
import styles from './profile.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700', '800'] })

export default function ProfilePage() {
  const { t } = useUI()
  const { user, refreshMe } = useAuth()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    if (!user) return
    setDisplayName(user.display_name || '')
    setEmail(user.email || '')
  }, [user])

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault()
    setSavingProfile(true)
    try {
      const res = await apiFetch('/api/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({
          display_name: displayName.trim(),
          email: email.trim(),
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(
          typeof data?.detail === 'string' ? data.detail : t('profileSaveFailed'),
        )
      }
      await refreshMe()
      notify.toast({
        title: t('profileSaved'),
        message: t('profileSaved'),
        tone: 'success',
        durationMs: 1500,
      })
    } catch (err) {
      notify.toast({
        title: t('profileSaveFailed'),
        message: err instanceof Error ? err.message : t('profileSaveFailed'),
        tone: 'error',
      })
    } finally {
      setSavingProfile(false)
    }
  }

  const changePassword = async (event: FormEvent) => {
    event.preventDefault()
    setSavingPassword(true)
    try {
      const res = await apiFetch('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(
          typeof data?.detail === 'string' ? data.detail : t('profilePasswordFailed'),
        )
      }
      setCurrentPassword('')
      setNewPassword('')
      notify.toast({
        title: t('profilePasswordChanged'),
        message: t('profilePasswordChanged'),
        tone: 'success',
        durationMs: 1500,
      })
    } catch (err) {
      notify.toast({
        title: t('profilePasswordFailed'),
        message: err instanceof Error ? err.message : t('profilePasswordFailed'),
        tone: 'error',
      })
    } finally {
      setSavingPassword(false)
    }
  }

  const name = (displayName || user?.display_name || user?.email || '—').trim() || '—'
  const shownEmail = (email || user?.email || '').trim()
  const initial = (name[0] || '?').toUpperCase()
  const isAdmin = user?.role === 'admin'

  return (
    <div
      className={`${styles.page} ${figtree.className}`}
      style={
        {
          '--profile-display': sora.style.fontFamily,
          '--profile-body': figtree.style.fontFamily,
        } as React.CSSProperties
      }
    >
      <header className={styles.header}>
        <div className={styles.avatar} aria-hidden="true">
          {initial}
        </div>
        <div className={styles.headerCopy}>
          <div className={styles.eyebrow}>{t('profileEyebrow')}</div>
          <h1 className={styles.name}>{name}</h1>
          {shownEmail ? <p className={styles.email}>{shownEmail}</p> : null}
          {isAdmin ? <p className={styles.adminNote}>{t('profileAdminNote')}</p> : null}
        </div>
      </header>

      <div className={styles.panel}>
        <section className={styles.block}>
          <div className={styles.blockHead}>
            <h2 className={styles.blockTitle}>{t('profileAccountSection')}</h2>
            <p className={styles.blockDesc}>{t('profileAccountDesc')}</p>
          </div>
          <form className={styles.form} onSubmit={saveProfile}>
            <label className={styles.field}>
              <span className={styles.label}>{t('profileDisplayName')}</span>
              <input
                className={styles.input}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={80}
                autoComplete="name"
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>{t('profileEmail')}</span>
              <input
                className={styles.input}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </label>
            <div className={styles.actions}>
              <button className={styles.btnPrimary} type="submit" disabled={savingProfile}>
                {savingProfile ? t('saving') : t('profileSave')}
              </button>
            </div>
          </form>
        </section>

        <section className={styles.block}>
          <div className={styles.blockHead}>
            <h2 className={styles.blockTitle}>{t('profilePasswordSection')}</h2>
            <p className={styles.blockDesc}>{t('profilePasswordDesc')}</p>
          </div>
          <form className={styles.form} onSubmit={changePassword}>
            <label className={styles.field}>
              <span className={styles.label}>{t('profileCurrentPassword')}</span>
              <input
                className={styles.input}
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>{t('profileNewPassword')}</span>
              <input
                className={styles.input}
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </label>
            <div className={styles.actions}>
              <button className={styles.btnPrimary} type="submit" disabled={savingPassword}>
                {savingPassword ? t('saving') : t('profileChangePassword')}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
