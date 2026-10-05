"use client"
import { useUI } from '@/lib/i18n'
import styles from './app-shell.module.css'

export default function LanguageSwitcher() {
  const { lang, setLang } = useUI()
  return (
    <div className={styles.langSwitch}>
      {(['tr', 'en'] as const).map(code => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          className={`${styles.langButton}${lang === code ? ` ${styles.langButtonActive}` : ''}`}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
