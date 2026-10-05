'use client'

import { FormEvent, Suspense, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Figtree, Sora } from 'next/font/google'
import { useAuth } from '@/lib/auth'
import { useUI } from '@/lib/i18n'
import LoginYeti from '@/components/auth/LoginYeti'
import styles from '../auth.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700'] })

function LoginForm() {
  const { t } = useUI()
  const { login } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const reason = searchParams.get('reason')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [passwordFocused, setPasswordFocused] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [emailInput, setEmailInput] = useState<HTMLInputElement | null>(null)
  const [passwordInput, setPasswordInput] = useState<HTMLInputElement | null>(null)

  const idleMessage = reason === 'idle' ? t('loginIdleMessage') : ''
  const coveringEyes = passwordFocused && !showPassword

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const user = await login(email.trim(), password)
      if (user.status === 'pending') {
        router.replace('/pending')
      } else if (user.status === 'rejected') {
        router.replace('/rejected')
      } else if (user.status === 'disabled') {
        setError(t('loginDisabled'))
      } else {
        router.replace('/')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loginError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={`${styles.card} ${styles.cardYeti}`}>
      <div className={styles.brand}>
        <img src="/logo.png?v=transparent" alt="Sunairum" className={styles.brandMark} width={40} height={40} />
        <span className={styles.brandName}>Sunairum</span>
      </div>

      <LoginYeti
        emailInput={emailInput}
        passwordInput={passwordInput}
        coverEyes={coveringEyes}
        className={styles.yeti}
      />

      <h1 className={styles.title}>{t('loginTitle')}</h1>
      <p className={styles.subtitle}>{t('loginSubtitle')}</p>

      {idleMessage ? <div className={`${styles.alert} ${styles.alertWarn}`}>{idleMessage}</div> : null}
      {error ? <div className={`${styles.alert} ${styles.alertError}`}>{error}</div> : null}

      <form className={styles.form} onSubmit={onSubmit}>
        <label className={styles.field}>
          <span className={styles.label}>{t('loginEmail')}</span>
          <input
            ref={setEmailInput}
            className={styles.input}
            type="text"
            autoComplete="username"
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>{t('loginPassword')}</span>
          <div className={styles.passwordRow}>
            <input
              ref={setPasswordInput}
              className={styles.input}
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={() => setPasswordFocused(true)}
              onBlur={() => setPasswordFocused(false)}
            />
            <button
              type="button"
              className={styles.passwordToggle}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => setShowPassword((v) => !v)}
              aria-pressed={showPassword}
              aria-label={showPassword ? t('loginHidePassword') : t('loginShowPassword')}
            >
              {showPassword ? t('loginHidePassword') : t('loginShowPassword')}
            </button>
          </div>
        </label>
        <button className={styles.submit} type="submit" disabled={submitting}>
          {submitting ? t('loginSigningIn') : t('loginSubmit')}
        </button>
      </form>

      <p className={styles.footer}>
        {t('loginNoAccount')}{' '}
        <Link href="/signup">{t('loginSignupLink')}</Link>
      </p>
    </div>
  )
}

export default function LoginPage() {
  return (
    <div className={`${styles.page} ${sora.className} ${figtree.className}`}>
      <Suspense fallback={<div className={`${styles.card} ${styles.cardYeti}`} />}>
        <LoginForm />
      </Suspense>
    </div>
  )
}
