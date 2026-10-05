'use client'

import { FormEvent, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Figtree, Sora } from 'next/font/google'
import { useAuth } from '@/lib/auth'
import { useUI } from '@/lib/i18n'
import { notify } from '@/components/feedback/notify'
import styles from '../auth.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700'] })

export default function SignupPage() {
  const { t } = useUI()
  const { signup } = useAuth()
  const router = useRouter()

  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await signup(email.trim(), password, displayName.trim())
      notify.toast({
        title: t('signupSuccessTitle'),
        message: t('signupSuccessMessage'),
        tone: 'success',
        durationMs: 4200,
      })
      router.replace('/login')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('signupError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={`${styles.page} ${sora.className} ${figtree.className}`}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <img src="/logo.png?v=transparent" alt="Sunairum" className={styles.brandMark} width={40} height={40} />
          <span className={styles.brandName}>Sunairum</span>
        </div>
        <h1 className={styles.title}>{t('signupTitle')}</h1>
        <p className={styles.subtitle}>{t('signupSubtitle')}</p>

        {error ? <div className={`${styles.alert} ${styles.alertError}`}>{error}</div> : null}

        <form className={styles.form} onSubmit={onSubmit}>
          <label className={styles.field}>
            <span className={styles.label}>{t('signupDisplayName')}</span>
            <input
              className={styles.input}
              type="text"
              autoComplete="name"
              name="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>{t('signupEmail')}</span>
            <input
              className={styles.input}
              type="email"
              autoComplete="email"
              name="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>{t('signupPassword')}</span>
            <input
              className={styles.input}
              type="password"
              autoComplete="new-password"
              name="password"
              minLength={8}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button className={styles.submit} type="submit" disabled={submitting}>
            {submitting ? t('signupSubmitting') : t('signupSubmit')}
          </button>
        </form>

        <p className={styles.footer}>
          {t('signupHasAccount')}{' '}
          <Link href="/login">{t('signupLoginLink')}</Link>
        </p>
      </div>
    </div>
  )
}
