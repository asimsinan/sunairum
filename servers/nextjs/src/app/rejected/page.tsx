'use client'

import { useRouter } from 'next/navigation'
import { Figtree, Sora } from 'next/font/google'
import { useAuth } from '@/lib/auth'
import { useUI } from '@/lib/i18n'
import Icon from '@/components/Icon'
import styles from '../auth.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700'] })

export default function RejectedPage() {
  const { t } = useUI()
  const { logout } = useAuth()
  const router = useRouter()

  const onLogout = async () => {
    await logout()
    router.replace('/login')
  }

  return (
    <div className={`${styles.page} ${sora.className} ${figtree.className}`}>
      <div className={styles.card}>
        <div className={styles.gateIcon}>
          <Icon name="x" className="w-6 h-6" />
        </div>
        <h1 className={styles.title}>{t('rejectedTitle')}</h1>
        <p className={styles.subtitle}>{t('rejectedMessage')}</p>
        <button type="button" className={styles.ghostBtn} onClick={onLogout}>
          {t('rejectedLogout')}
        </button>
      </div>
    </div>
  )
}
