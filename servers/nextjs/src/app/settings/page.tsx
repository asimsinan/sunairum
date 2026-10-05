"use client"

import { useState, useEffect, useCallback, useRef } from 'react'
import { Figtree, Sora } from 'next/font/google'
import { useUI } from '@/lib/i18n'
import { apiFetch } from '@/lib/api'
import { notify } from '@/components/feedback/notify'
import Icon from '@/components/Icon'
import styles from './settings.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700'] })

type ProbeResult = {
  ok: boolean
  skipped?: boolean
  model?: string
  latency_ms?: number
  detail?: string
}

type ConnectionState = 'idle' | 'testing' | 'ok' | 'partial' | 'error'
type SectionId = 'provider' | 'image' | 'connection'
type ImageProvider = 'openrouter' | 'openai'

const BANNED_GOOGLE_RE = /(?:^|\/)(google|gemini)\b|generativelanguage\.googleapis\.com/i

function isBannedGoogleString(value: string) {
  return BANNED_GOOGLE_RE.test((value || '').trim())
}

export default function Settings() {
  const { t } = useUI()
  const provider = 'openai_compatible'
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState('')
  const [imageProvider, setImageProvider] = useState<ImageProvider>('openrouter')
  const [imageModelName, setImageModelName] = useState('')
  const [imageBaseUrl, setImageBaseUrl] = useState('')
  const [imageApiKey, setImageApiKey] = useState('')
  const [imageDefaults, setImageDefaults] = useState({
    model_name: 'qwen/qwen-image-3',
    base_url: 'https://openrouter.ai/api/v1',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle')
  const [textProbe, setTextProbe] = useState<ProbeResult | null>(null)
  const [imageProbe, setImageProbe] = useState<ProbeResult | null>(null)
  const [connectionStale, setConnectionStale] = useState(false)
  const [connectionTestedAt, setConnectionTestedAt] = useState<number | null>(null)
  const [activeSection, setActiveSection] = useState<SectionId>('provider')

  const providerRef = useRef<HTMLElement | null>(null)
  const imageRef = useRef<HTMLElement | null>(null)
  const connectionRef = useRef<HTMLElement | null>(null)

  const applyConnectionTest = useCallback((test: any | null | undefined) => {
    if (!test || typeof test !== 'object') return
    const status = test.status
    if (status === 'ok' || status === 'partial' || status === 'error') {
      setConnectionState(status)
    }
    setTextProbe(test.text || null)
    setImageProbe(test.image || null)
    setConnectionStale(Boolean(test.stale))
    setConnectionTestedAt(
      typeof test.tested_at === 'number' && Number.isFinite(test.tested_at)
        ? test.tested_at
        : null,
    )
  }, [])

  useEffect(() => {
    apiFetch('/api/settings')
      .then((res) => res.json())
      .then((data) => {
        if (!data) return
        setBaseUrl(data.base_url || '')
        setApiKey(data.api_key || '')
        setModelName(data.model_name || '')
        const nextImage = (data.image_provider || 'openrouter') as ImageProvider
        setImageProvider(nextImage === 'openai' ? 'openai' : 'openrouter')
        setImageModelName(data.image_model_name || '')
        setImageBaseUrl(data.image_base_url || '')
        setImageApiKey(data.image_api_key || '')
        if (data.image_defaults) {
          setImageDefaults({
            model_name: data.image_defaults.model_name || 'qwen/qwen-image-3',
            base_url: data.image_defaults.base_url || 'https://openrouter.ai/api/v1',
          })
        }
        applyConnectionTest(data.connection_test)
      })
      .catch((err) => console.error('Error loading settings', err))
      .finally(() => setLoading(false))
  }, [applyConnectionTest])

  useEffect(() => {
    const placeholders: Record<ImageProvider, { model_name: string; base_url: string }> = {
      openrouter: {
        model_name: 'qwen/qwen-image-3',
        base_url: 'https://openrouter.ai/api/v1',
      },
      openai: {
        model_name: 'gpt-image-2',
        base_url: 'https://api.openai.com/v1',
      },
    }
    setImageDefaults(placeholders[imageProvider])
  }, [imageProvider])

  useEffect(() => {
    const nodes = [
      { id: 'provider' as const, el: providerRef.current },
      { id: 'image' as const, el: imageRef.current },
      { id: 'connection' as const, el: connectionRef.current },
    ].filter((item) => item.el)

    if (!nodes.length) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (!visible?.target) return
        const id = (visible.target as HTMLElement).dataset.section as SectionId | undefined
        if (id) setActiveSection(id)
      },
      { rootMargin: '-20% 0px -55% 0px', threshold: [0.2, 0.5, 0.8] },
    )

    nodes.forEach((item) => observer.observe(item.el!))
    return () => observer.disconnect()
  }, [loading])

  const resetConnection = useCallback(() => {
    // Form drift invalidates the last saved probe until the next test.
    setConnectionState('idle')
    setTextProbe(null)
    setImageProbe(null)
    setConnectionStale(false)
    setConnectionTestedAt(null)
  }, [])

  const scrollToSection = (id: SectionId) => {
    const map = {
      provider: providerRef,
      image: imageRef,
      connection: connectionRef,
    }
    map[id].current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setActiveSection(id)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    const bannedField =
      [modelName, baseUrl, imageModelName, imageBaseUrl].find(
        isBannedGoogleString,
      ) || ''
    if (bannedField) {
      notify.toast({
        title: t('settingsSaveFailed'),
        message: t('settingsGoogleBanned'),
        tone: 'error',
      })
      return
    }
    if (!baseUrl.trim() || !modelName.trim() || !apiKey.trim()) {
      notify.toast({
        title: t('settingsSaveFailed'),
        message: t('settingsTextRequired'),
        tone: 'error',
      })
      return
    }
    setSaving(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({
          provider: 'openai_compatible',
          base_url: baseUrl,
          api_key: apiKey,
          model_name: modelName,
          image_provider: imageProvider,
          image_model_name: imageModelName,
          image_base_url: imageBaseUrl,
          image_api_key: imageApiKey,
        }),
      })

      if (res.ok) {
        notify.toast({
          title: t('settingsSavedTitle'),
          message: t('saved'),
          tone: 'success',
          durationMs: 1500,
        })
      } else {
        const data = await res.json().catch(() => null)
        notify.toast({
          title: t('settingsSaveFailed'),
          message:
            typeof data?.detail === 'string' ? data.detail : t('settingsSaveHint'),
          tone: 'error',
        })
      }
    } catch (err) {
      console.error('Error saving settings', err)
      notify.toast({
        title: t('settingsSaveFailed'),
        message: err instanceof Error ? err.message : t('settingsSaveHint'),
        tone: 'error',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleTestConnection = async () => {
    setConnectionState('testing')
    setTextProbe(null)
    setImageProbe(null)
    scrollToSection('connection')
    try {
      const res = await apiFetch('/api/settings/test', {
        method: 'POST',
        body: JSON.stringify({
          provider,
          base_url: baseUrl,
          api_key: apiKey,
          model_name: modelName,
          image_provider: imageProvider,
          image_model_name: imageModelName,
          image_base_url: imageBaseUrl,
          image_api_key: imageApiKey,
          test_image: true,
        }),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok || !data) {
        setConnectionState('error')
        setTextProbe({
          ok: false,
          detail: typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`,
        })
        notify.toast({
          title: t('settingsConnectionError'),
          message: typeof data?.detail === 'string' ? data.detail : t('settingsSaveFailed'),
          tone: 'error',
        })
        return
      }

      applyConnectionTest(data)
      const next =
        data.status === 'ok' ? 'ok' : data.status === 'partial' ? 'partial' : 'error'
      notify.toast({
        title:
          next === 'ok'
            ? t('settingsConnectionOk')
            : next === 'partial'
              ? t('settingsConnectionPartial')
              : t('settingsConnectionError'),
        message:
          next === 'ok'
            ? data.text?.detail || t('saved')
            : data.text?.ok
              ? data.image?.detail || t('settingsConnectionPartial')
              : data.text?.detail || t('settingsConnectionError'),
        tone: next === 'ok' ? 'success' : 'error',
        durationMs: 1600,
      })
    } catch (err) {
      setConnectionState('error')
      setTextProbe({
        ok: false,
        detail: err instanceof Error ? err.message : t('settingsConnectionError'),
      })
      setConnectionStale(false)
      notify.toast({
        title: t('settingsConnectionError'),
        message: err instanceof Error ? err.message : t('settingsSaveFailed'),
        tone: 'error',
      })
    }
  }

  const statusLabel =
    connectionState === 'testing'
      ? t('settingsConnectionTesting')
      : connectionState === 'ok'
        ? t('settingsConnectionOk')
        : connectionState === 'partial'
          ? t('settingsConnectionPartial')
          : connectionState === 'error'
            ? t('settingsConnectionError')
            : t('settingsConnectionIdle')

  const statusSub =
    connectionState === 'testing'
      ? t('settingsTestingConnection')
      : connectionStale
        ? t('settingsConnectionStale')
        : connectionTestedAt
          ? t('settingsConnectionLastTested', {
              time: new Date(connectionTestedAt * 1000).toLocaleString(),
            })
          : connectionState === 'idle'
            ? t('settingsTestConnection')
            : textProbe?.detail ||
              imageProbe?.detail ||
              t('settingsSaveHint')

  const providerLabel = t('providerOpenAI')

  const imageProviderLabel =
    imageProvider === 'openai' ? t('imageProviderOpenAI') : t('imageProviderOpenRouter')

  const imageModelPlaceholder =
    imageDefaults.model_name ||
    (imageProvider === 'openai' ? 'gpt-image-2' : 'qwen/qwen-image-3')

  if (loading) {
    return (
      <div className={`${styles.page} ${figtree.className}`}>
        <div className={styles.loading}>
          <div className={styles.loadingPulse} aria-hidden="true" />
          {t('loading')}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`${styles.page} ${figtree.className}`}
      style={
        {
          '--settings-display': sora.style.fontFamily,
          '--settings-body': figtree.style.fontFamily,
        } as React.CSSProperties
      }
    >
      <header className={styles.hero}>
        <div className={styles.heroTop}>
          <div>
            <div className={styles.eyebrow}>
              <span className={styles.eyebrowMark} aria-hidden="true" />
              {t('settingsEyebrow')}
            </div>
            <h1 className={styles.title}>{t('settingsTitle')}</h1>
            <p className={styles.subtitle}>{t('settingsSubtitle')}</p>
          </div>
          <div className={styles.heroMeta}>
            <span className={styles.heroMetaLabel}>{t('provider')}</span>
            <span className={styles.heroMetaValue}>{providerLabel}</span>
          </div>
        </div>
      </header>

      <div className={styles.shell}>
        <nav className={styles.nav} aria-label={t('settingsTitle')}>
          <button
            type="button"
            className={styles.navBtn}
            data-active={activeSection === 'provider'}
            onClick={() => scrollToSection('provider')}
          >
            <span className={styles.navIcon} aria-hidden="true">
              <Icon name="sparkles" className="w-3.5 h-3.5" />
            </span>
            {t('settingsPanelTitle')}
          </button>
          <button
            type="button"
            className={styles.navBtn}
            data-active={activeSection === 'image'}
            onClick={() => scrollToSection('image')}
          >
            <span className={styles.navIcon} aria-hidden="true">
              <Icon name="image" className="w-3.5 h-3.5" />
            </span>
            {t('imageSectionTitle')}
          </button>
          <button
            type="button"
            className={styles.navBtn}
            data-active={activeSection === 'connection'}
            onClick={() => scrollToSection('connection')}
          >
            <span className={styles.navIcon} aria-hidden="true">
              <Icon name="globe" className="w-3.5 h-3.5" />
            </span>
            {t('settingsConnection')}
          </button>
        </nav>

        <form id="settings-form" onSubmit={handleSave} className={styles.content}>
          <section
            ref={providerRef}
            className={styles.panel}
            data-section="provider"
            id="settings-provider"
          >
            <header className={styles.panelHead}>
              <div className={styles.panelHeadMain}>
                <div className={styles.panelGlyph} aria-hidden="true">
                  <Icon name="sparkles" className="w-4 h-4" />
                </div>
                <div>
                  <h2 className={styles.panelTitle}>{t('settingsPanelTitle')}</h2>
                  <p className={styles.panelDesc}>{t('settingsPanelDesc')}</p>
                </div>
              </div>
            </header>
            <div className={styles.panelBody}>
              <div className={styles.field}>
                <div className={styles.labelRow}>
                  <label className={styles.label}>{t('provider')}</label>
                </div>
                <p className={styles.hint}>{t('settingsProviderHint')}</p>
                <p className={styles.heroMetaValue}>{providerLabel}</p>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="settings-base-url">
                  {t('baseUrl')}
                </label>
                <input
                  id="settings-base-url"
                  type="text"
                  value={baseUrl}
                  required
                  onChange={(e) => {
                    setBaseUrl(e.target.value)
                    resetConnection()
                  }}
                  placeholder={t('baseUrlPlaceholder')}
                  className={styles.input}
                />
                <span className={styles.hint}>{t('baseUrlHint')}</span>
              </div>

              <div className={styles.fieldRow}>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="settings-api-key">
                    {t('apiKey')}
                  </label>
                  <input
                    id="settings-api-key"
                    type="password"
                    value={apiKey}
                    required
                    onChange={(e) => {
                      setApiKey(e.target.value)
                      resetConnection()
                    }}
                    placeholder={t('apiKeyPlaceholder')}
                    className={styles.input}
                    autoComplete="off"
                  />
                  <span className={styles.hint}>{t('settingsApiHint')}</span>
                </div>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="settings-model">
                    {t('modelName')}
                  </label>
                  <input
                    id="settings-model"
                    type="text"
                    value={modelName}
                    required
                    onChange={(e) => {
                      setModelName(e.target.value)
                      resetConnection()
                    }}
                    placeholder={t('openAIModelPlaceholder')}
                    className={styles.input}
                  />
                </div>
              </div>
            </div>
          </section>

          <section
            ref={imageRef}
            className={styles.panel}
            data-section="image"
            id="settings-image"
          >
            <header className={styles.panelHead}>
              <div className={styles.panelHeadMain}>
                <div className={styles.panelGlyph} aria-hidden="true">
                  <Icon name="image" className="w-4 h-4" />
                </div>
                <div>
                  <h2 className={styles.panelTitle}>{t('imageSectionTitle')}</h2>
                  <p className={styles.panelDesc}>{t('imageSectionDesc')}</p>
                </div>
              </div>
            </header>
            <div className={styles.panelBody}>
              <div className={styles.field}>
                <div className={styles.labelRow}>
                  <label className={styles.label}>{t('imageProvider')}</label>
                </div>
                <div className={styles.segment} role="radiogroup" aria-label={t('imageProvider')}>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={imageProvider === 'openrouter'}
                    className={styles.segmentBtn}
                    data-active={imageProvider === 'openrouter'}
                    onClick={() => {
                      setImageProvider('openrouter')
                      resetConnection()
                    }}
                  >
                    <strong>{t('imageProviderOpenRouter')}</strong>
                    <span>{t('imageProviderHint')}</span>
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={imageProvider === 'openai'}
                    className={styles.segmentBtn}
                    data-active={imageProvider === 'openai'}
                    onClick={() => {
                      setImageProvider('openai')
                      resetConnection()
                    }}
                  >
                    <strong>{t('imageProviderOpenAI')}</strong>
                    <span>{t('imageProviderHint')}</span>
                  </button>
                </div>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="settings-image-model">
                  {t('imageModelName')}
                </label>
                <input
                  id="settings-image-model"
                  type="text"
                  value={imageModelName}
                  onChange={(e) => {
                    setImageModelName(e.target.value)
                    resetConnection()
                  }}
                  placeholder={imageModelPlaceholder}
                  className={styles.input}
                />
                <span className={styles.hint}>{t('imageModelHint')}</span>
              </div>

              <div className={styles.fieldRow}>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="settings-image-url">
                    {t('imageBaseUrl')}
                  </label>
                  <input
                    id="settings-image-url"
                    type="text"
                    value={imageBaseUrl}
                    onChange={(e) => {
                      setImageBaseUrl(e.target.value)
                      resetConnection()
                    }}
                    placeholder={imageDefaults.base_url || t('baseUrlPlaceholder')}
                    className={styles.input}
                  />
                  <span className={styles.hint}>{t('imageBaseUrlHint')}</span>
                </div>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="settings-image-key">
                    {t('imageApiKey')}
                  </label>
                  <input
                    id="settings-image-key"
                    type="password"
                    value={imageApiKey}
                    onChange={(e) => {
                      setImageApiKey(e.target.value)
                      resetConnection()
                    }}
                    placeholder={t('apiKeyPlaceholder')}
                    className={styles.input}
                    autoComplete="off"
                  />
                  <span className={styles.hint}>{t('imageApiKeyHint')}</span>
                </div>
              </div>
            </div>
          </section>

          <section
            ref={connectionRef}
            className={styles.panel}
            data-section="connection"
            id="settings-connection"
          >
            <header className={styles.panelHead}>
              <div className={styles.panelHeadMain}>
                <div className={styles.panelGlyph} aria-hidden="true">
                  <Icon name="globe" className="w-4 h-4" />
                </div>
                <div>
                  <h2 className={styles.panelTitle}>{t('settingsConnection')}</h2>
                  <p className={styles.panelDesc}>{t('settingsPanelDesc')}</p>
                </div>
              </div>
            </header>
            <div className={styles.panelBody}>
              <div className={styles.connectionCard}>
                <div className={styles.statusHero} data-state={connectionState}>
                  <div className={styles.statusOrb} aria-hidden="true">
                    <span className={styles.statusOrbDot} />
                  </div>
                  <div className={styles.statusCopy}>
                    <p className={styles.statusTitle}>{statusLabel}</p>
                    <p className={styles.statusSub}>{statusSub}</p>
                  </div>
                </div>

                {(textProbe || imageProbe) && (
                  <div className={styles.probeGrid}>
                    {textProbe && (
                      <div
                        className={styles.probeCard}
                        data-ok={textProbe.ok ? 'true' : 'false'}
                      >
                        <span className={styles.probeLabel}>{t('settingsTestTextLabel')}</span>
                        <span className={styles.probeValue}>
                          {textProbe.ok ? `${textProbe.latency_ms ?? 0} ms` : '—'}
                        </span>
                        <span className={styles.probeDetail}>
                          {textProbe.ok
                            ? textProbe.model || providerLabel
                            : textProbe.detail || t('settingsConnectionError')}
                        </span>
                      </div>
                    )}
                    {imageProbe && (
                      <div
                        className={styles.probeCard}
                        data-ok={
                          imageProbe.skipped ? 'skip' : imageProbe.ok ? 'true' : 'false'
                        }
                      >
                        <span className={styles.probeLabel}>{t('settingsTestImageLabel')}</span>
                        <span className={styles.probeValue}>
                          {imageProbe.skipped
                            ? t('settingsTestSkipped')
                            : imageProbe.ok
                              ? `${imageProbe.latency_ms ?? 0} ms`
                              : '—'}
                        </span>
                        <span className={styles.probeDetail}>
                          {imageProbe.skipped
                            ? imageProbe.detail
                            : imageProbe.ok
                              ? imageProbe.model || imageProviderLabel
                              : imageProbe.detail || t('settingsConnectionError')}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>
        </form>
      </div>

      <div className={styles.dock}>
        <p className={styles.dockHint}>{t('settingsSaveHint')}</p>
        <div className={styles.dockActions}>
          <button
            type="button"
            className={styles.btnSecondary}
            disabled={connectionState === 'testing' || saving}
            onClick={handleTestConnection}
          >
            <Icon name="globe" className="w-3.5 h-3.5" />
            {connectionState === 'testing'
              ? t('settingsTestingConnection')
              : t('settingsTestConnection')}
          </button>
          <button
            type="submit"
            form="settings-form"
            className={styles.btnPrimary}
            disabled={saving || connectionState === 'testing'}
          >
            <Icon name="save" className="w-3.5 h-3.5" />
            {saving ? t('saving') : t('saveBtn')}
          </button>
        </div>
      </div>
    </div>
  )
}
