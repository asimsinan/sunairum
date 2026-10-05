"use client"
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Figtree, Sora } from 'next/font/google'
import { useUI } from '@/lib/i18n'
import { API_URL, apiFetch } from '@/lib/api'
import { useWizardStore } from '@/store/wizardStore'
import { setPendingSourceUpload } from '@/lib/pendingSourceUpload'
import Icon from '@/components/Icon'
import SlideLightbox, { lightboxStyles } from '@/components/SlideLightbox'
import styles from './home.module.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'], variable: '--font-sora' })
const figtree = Figtree({
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
  variable: '--font-figtree',
})

const LANGUAGES = [
  { code: 'auto', label: 'Otomatik', name: 'Auto' },
  { code: 'tr', label: 'Türkçe', name: 'Türkçe' },
  { code: 'en', label: 'English', name: 'English' },
  { code: 'es', label: 'Español', name: 'Spanish' },
  { code: 'fr', label: 'Français', name: 'French' },
  { code: 'de', label: 'Deutsch', name: 'German' },
  { code: 'pt', label: 'Português', name: 'Portuguese' },
  { code: 'it', label: 'Italiano', name: 'Italian' },
  { code: 'nl', label: 'Nederlands', name: 'Dutch' },
  { code: 'ru', label: 'Русский', name: 'Russian' },
  { code: 'pl', label: 'Polski', name: 'Polish' },
  { code: 'uk', label: 'Українська', name: 'Ukrainian' },
  { code: 'el', label: 'Ελληνικά', name: 'Greek' },
  { code: 'cs', label: 'Čeština', name: 'Czech' },
  { code: 'sv', label: 'Svenska', name: 'Swedish' },
  { code: 'da', label: 'Dansk', name: 'Danish' },
  { code: 'no', label: 'Norsk', name: 'Norwegian' },
  { code: 'fi', label: 'Suomi', name: 'Finnish' },
  { code: 'hu', label: 'Magyar', name: 'Hungarian' },
  { code: 'ro', label: 'Română', name: 'Romanian' },
  { code: 'bg', label: 'Български', name: 'Bulgarian' },
  { code: 'sr', label: 'Српски', name: 'Serbian' },
  { code: 'hr', label: 'Hrvatski', name: 'Croatian' },
  { code: 'sk', label: 'Slovenčina', name: 'Slovak' },
  { code: 'et', label: 'Eesti', name: 'Estonian' },
  { code: 'lv', label: 'Latviešu', name: 'Latvian' },
  { code: 'lt', label: 'Lietuvių', name: 'Lithuanian' },
  { code: 'zh-CN', label: '中文', name: 'Chinese Simplified' },
  { code: 'zh-TW', label: '繁體中文', name: 'Chinese Traditional' },
  { code: 'ja', label: '日本語', name: 'Japanese' },
  { code: 'ko', label: '한국어', name: 'Korean' },
  { code: 'ar', label: 'العربية', name: 'Arabic' },
  { code: 'he', label: 'עברית', name: 'Hebrew' },
  { code: 'fa', label: 'فارسی', name: 'Persian/Farsi' },
  { code: 'hi', label: 'हिन्दी', name: 'Hindi' },
  { code: 'bn', label: 'বাংলা', name: 'Bengali' },
  { code: 'ur', label: 'اردو', name: 'Urdu' },
  { code: 'ta', label: 'தமிழ்', name: 'Tamil' },
  { code: 'te', label: 'తెలుగు', name: 'Telugu' },
  { code: 'mr', label: 'मराठी', name: 'Marathi' },
  { code: 'pa', label: 'ਪੰਜਾਬੀ', name: 'Punjabi' },
  { code: 'gu', label: 'ગુજરાતી', name: 'Gujarati' },
  { code: 'kn', label: 'ಕನ್ನಡ', name: 'Kannada' },
  { code: 'ml', label: 'മലയാളം', name: 'Malayalam' },
  { code: 'si', label: 'සිංහල', name: 'Sinhala' },
  { code: 'ne', label: 'नेपाली', name: 'Nepali' },
  { code: 'th', label: 'ไทย', name: 'Thai' },
  { code: 'vi', label: 'Tiếng Việt', name: 'Vietnamese' },
  { code: 'id', label: 'Bahasa Indonesia', name: 'Indonesian' },
  { code: 'ms', label: 'Bahasa Melayu', name: 'Malay' },
  { code: 'fil', label: 'Filipino', name: 'Filipino' },
  { code: 'az', label: 'Azərbaycan', name: 'Azerbaijani' },
  { code: 'kk', label: 'Қазақша', name: 'Kazakh' },
  { code: 'uz', label: 'Oʻzbek', name: 'Uzbek' },
  { code: 'tk', label: 'Türkmençe', name: 'Turkmen' },
  { code: 'ku', label: 'Kurdî', name: 'Kurdish' },
  { code: 'ps', label: 'پښتو', name: 'Pashto' },
  { code: 'mn', label: 'Монгол', name: 'Mongolian' },
  { code: 'ka', label: 'ქართული', name: 'Georgian' },
  { code: 'hy', label: 'Հայերեն', name: 'Armenian' },
  { code: 'sq', label: 'Shqip', name: 'Albanian' },
  { code: 'bs', label: 'Bosanski', name: 'Bosnian' },
  { code: 'mk', label: 'Македонски', name: 'Macedonian' },
  { code: 'is', label: 'Íslenska', name: 'Icelandic' },
  { code: 'cy', label: 'Cymraeg', name: 'Welsh' },
  { code: 'ga', label: 'Gaeilge', name: 'Irish' },
  { code: 'sw', label: 'Kiswahili', name: 'Swahili' },
  { code: 'am', label: 'አማርኛ', name: 'Amharic' },
]

const SLIDE_OPTIONS = ['5', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20']
const MAX_NUMBER_OF_SLIDES = 50

/** Scratch presentation styles — shipped client-side so the picker paints with the composer (no post-load pop-in). */
const PRESENTATION_STYLES: { id: string; summary: string }[] = [
  { id: 'academic-research', summary: '' },
  { id: 'consulting-decision', summary: '' },
  { id: 'creative-pitch', summary: '' },
  { id: 'incident-postmortem', summary: '' },
  { id: 'investor-pitch', summary: '' },
  { id: 'narrative-keynote', summary: '' },
  { id: 'operating-review', summary: '' },
  { id: 'product-launch', summary: '' },
  { id: 'science-explainer', summary: '' },
  { id: 'solution-proposal', summary: '' },
  { id: 'technical-deepdive', summary: '' },
  { id: 'workshop-teaching', summary: '' },
]

export default function Home() {
  const { t } = useUI()
  const [topic, setTopic] = useState('')
  const [instructions, setInstructions] = useState('')
  const [instructionsOpen, setInstructionsOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [language, setLanguage] = useState('auto')
  const [slideCount, setSlideCount] = useState('auto')
  const [customSlides, setCustomSlides] = useState('')
  const [langOpen, setLangOpen] = useState(false)
  const [slidesOpen, setSlidesOpen] = useState(false)
  const [langQuery, setLangQuery] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [templates, setTemplates] = useState<any[]>([])
  const [templateQuery, setTemplateQuery] = useState('')
  const [templateStyle, setTemplateStyle] = useState('all')
  const [selectedTemplate, setSelectedTemplate] = useState<{ id: string; color: string; title: string } | null>(null)
  const [presentationStyles, setPresentationStyles] = useState(PRESENTATION_STYLES)
  const [selectedStyleId, setSelectedStyleId] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ id: string; title: string; color: string; available: boolean } | null>(null)
  const [previewSlides, setPreviewSlides] = useState<string[]>([])
  const [previewIndex, setPreviewIndex] = useState(0)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [promptError, setPromptError] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const router = useRouter()
  const setWizardConfig = useWizardStore((s) => s.setConfig)

  useEffect(() => {
    // ppt-master example packs as design references (free_design inspiration).
    apiFetch('/api/templates')
      .then(res => res.json())
      .then(data => {
        if (data && data.projects) {
          setTemplates(data.projects)
        }
      })
      .catch(err => console.error("Error loading templates", err))
    apiFetch('/api/styles')
      .then(res => res.json())
      .then(data => {
        if (data && Array.isArray(data.styles)) {
          setPresentationStyles(data.styles)
        }
      })
      .catch(err => console.error("Error loading styles", err))
  }, [])

  useEffect(() => {
    // Soft-nav CSS-chunk miss: layout/sidebar styles apply, home.module.css does not.
    // Detect once and hard-reload; session flag prevents a loop.
    const root = document.querySelector<HTMLElement>('[data-home-root]')
    if (!root) return
    const maxWidth = getComputedStyle(root).maxWidth
    const key = 'sunairum_home_css_reload'
    if (!maxWidth || maxWidth === 'none') {
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1')
        window.location.reload()
      }
      return
    }
    sessionStorage.removeItem(key)
  }, [])

  const getSlideCountParam = () => {
    if (slideCount === 'custom') {
      const n = parseInt(customSlides, 10)
      if (!isNaN(n)) return String(Math.min(Math.max(n, 3), MAX_NUMBER_OF_SLIDES))
      return 'auto'
    }
    return slideCount
  }

  const startProject = (mode: string, templateId?: string, color?: string) => {
    if (isStarting) return
    setIsStarting(true)
    const projectId = "proj_" + Math.random().toString(36).substring(7)

    // Navigate first; PDF bytes upload on the editor "Preparing source" page
    // so the Get Started button never sits on "Uploading...".
    if (file) {
      setPendingSourceUpload({
        projectId,
        file,
        topic: topic || file.name,
      })
    }

    // Wizard config travels via the sessionStorage-backed store (SPA style):
    // no query params in the URL, no page refresh, live state in-memory.
    setWizardConfig({
      projectId,
      entry: 'create',
      topic: topic || (file ? file.name : ''),
      mode: (mode === 'template' ? 'template' : 'scratch'),
      templateId: templateId || undefined,
      color: color || undefined,
      lang: language,
      slides: getSlideCountParam(),
      hasSource: Boolean(file),
      instructions: instructions.trim() || undefined,
      styleId:
        mode === 'template' ? undefined : selectedStyleId || undefined,
    })
    router.push(`/editor/${projectId}`)
    // Keep isStarting true until unmount — clearing it before navigate
    // flashed Generate ↔ Starting and looked like a button flick.
  }

  const handleGenerate = () => {
    if (isStarting) return
    if (!canGenerate) {
      setPromptError(true)
      promptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      promptRef.current?.focus()
      return
    }
    if (selectedTemplate) {
      void startProject('template', selectedTemplate.id, selectedTemplate.color)
      return
    }
    void startProject('scratch')
  }

  const handleSelectTemplate = (templateId: string, color: string, title: string) => {
    // Selection only — Get Started is the sole pipeline entry.
    setSelectedTemplate(current => {
      if (current?.id === templateId) return null
      setSelectedStyleId(null) // style picker is scratch-only
      return { id: templateId, color, title }
    })
  }

  const openTemplatePreview = async (tpl: { id: string; title: string; color?: string; available?: boolean }) => {
    setPreview({
      id: tpl.id,
      title: tpl.title,
      color: tpl.color || '#000',
      available: Boolean(tpl.available),
    })
    setPreviewSlides([])
    setPreviewIndex(0)
    setPreviewLoading(true)
    try {
      const res = await apiFetch(`/api/templates/${tpl.id}/slides`)
      if (!res.ok) throw new Error('preview unavailable')
      const data = await res.json()
      setPreviewSlides(Array.isArray(data.slides) ? data.slides : [])
    } catch {
      setPreviewSlides([])
    } finally {
      setPreviewLoading(false)
    }
  }

  const closeTemplatePreview = () => {
    setPreview(null)
    setPreviewSlides([])
    setPreviewIndex(0)
  }

  useEffect(() => {
    if (!preview) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeTemplatePreview()
      if (event.key === 'ArrowLeft') setPreviewIndex(index => Math.max(0, index - 1))
      if (event.key === 'ArrowRight') {
        setPreviewIndex(index => Math.min(Math.max(previewSlides.length - 1, 0), index + 1))
      }
    }
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [preview, previewSlides.length])

  const canGenerate = !!(topic.trim() || file)
  const selectedLang = LANGUAGES.find(l => l.code === language)
  const filteredLangs = LANGUAGES.filter(l =>
    l.name.toLowerCase().includes(langQuery.toLowerCase()) ||
    l.label.toLowerCase().includes(langQuery.toLowerCase())
  )
  const filteredTemplates = templates.filter(template => {
    const query = templateQuery.trim().toLowerCase()
    const matchesQuery = !query || `${template.title} ${template.description} ${(template.tags || []).join(' ')}`.toLowerCase().includes(query)
    const matchesStyle = templateStyle === 'all' || template.style === templateStyle
    return matchesQuery && matchesStyle
  })
  const templateStyles = Array.from(new Set(templates.map(template => template.style).filter(Boolean))).slice(0, 5)
  const templateStyleLabel = (style: string) => {
    const key = `style${style.charAt(0).toUpperCase()}${style.slice(1)}`
    const label = t(key)
    return label === key ? style.charAt(0).toUpperCase() + style.slice(1) : label
  }
  const styleKeySuffix = (styleId: string) =>
    styleId
      .split('-')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join('')
  const presentationStyleLabel = (styleId: string) => {
    const key = `presStyle${styleKeySuffix(styleId)}`
    const label = t(key)
    return label === key
      ? styleId
          .split('-')
          .map(part => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' ')
      : label
  }
  const presentationStyleSummary = (styleId: string, fallback: string) => {
    const key = `presStyleSummary${styleKeySuffix(styleId)}`
    const label = t(key)
    return label === key ? fallback : label
  }

  return (
    <div
      data-home-root
      className={`${styles.page} ${sora.variable} ${figtree.variable} ${figtree.className}`}
    >
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}><span className={styles.eyebrowMark} />{t('studioEyebrow')}</div>
          <h1 className={styles.title}>Sunairum</h1>
          <p className={styles.subtitle}>{t('heroSubtitle')}</p>
        </div>
      </header>

      <div className={styles.workspace}>
        <section className={styles.composer}>
          <div className={styles.composerHeader}>
            <div className={styles.composerLabel}><span className={styles.composerLabelIcon}><Icon name="pencil" className="w-4 h-4" /></span>{t('promptLabel')}</div>
            <span className={styles.composerHint}>{t('composerHint')}</span>
          </div>
          <textarea
            ref={promptRef}
            value={topic}
            onChange={(e) => { setTopic(e.target.value); if (promptError && (e.target.value.trim() || file)) setPromptError(false) }}
            placeholder={t('promptPlaceholder')}
            rows={6}
            className={`${styles.prompt} ${promptError ? styles.promptError : ''}`}
          />
          {promptError && <p className={styles.promptErrorText}>{t('promptRequired')}</p>}
          {!selectedTemplate && presentationStyles.length > 0 && (
            <div className={styles.stylePicker}>
              <div className={styles.stylePickerChips} role="listbox" aria-label={t('presentationStyleLabel')}>
                <button
                  type="button"
                  role="option"
                  aria-selected={!selectedStyleId}
                  onClick={() => setSelectedStyleId(null)}
                  className={`${styles.styleChip} ${!selectedStyleId ? styles.styleChipActive : ''}`}
                >
                  {t('presentationStyleAuto')}
                </button>
                {presentationStyles.map(style => {
                  const active = selectedStyleId === style.id
                  const label = presentationStyleLabel(style.id)
                  return (
                    <button
                      key={style.id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      title={presentationStyleSummary(style.id, style.summary)}
                      onClick={() =>
                        setSelectedStyleId(current => (current === style.id ? null : style.id))
                      }
                      className={`${styles.styleChip} ${active ? styles.styleChipActive : ''}`}
                    >
                      {label}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
          <div className={styles.instructionsBlock}>
            <button
              type="button"
              onClick={() => setInstructionsOpen(open => !open)}
              className={styles.instructionsToggle}
              aria-expanded={instructionsOpen}
            >
              <Icon name="plus" className="w-4 h-4" />
              {t('instructionsLabel')}
              {!instructionsOpen && instructions.trim() && <span className={styles.instructionsDot} />}
              <span className={styles.instructionsChevron} data-open={instructionsOpen}>⌄</span>
            </button>
            {instructionsOpen && (
              <>
                <textarea
                  value={instructions}
                  onChange={e => setInstructions(e.target.value)}
                  placeholder={t('instructionsPlaceholder')}
                  rows={3}
                  className={styles.instructions}
                />
                <p className={styles.instructionsHint}>{t('instructionsHint')}</p>
              </>
            )}
          </div>
          <div className={styles.controlRow}>
            <div className="relative">
              <button
                type="button"
                onClick={() => { setLangOpen(!langOpen); setSlidesOpen(false) }}
                className={styles.controlButton}
              >
                <Icon name="globe" className={`w-4 h-4 ${styles.controlButtonIcon}`} />
                {language === 'auto' ? t('autoLang') : selectedLang?.label || t('autoLang')}
                <span>⌄</span>
              </button>
              {langOpen && (
                <div className={`${styles.controlMenu} ${styles.controlMenuWide}`}>
                  <input
                    autoFocus
                    value={langQuery}
                    onChange={e => setLangQuery(e.target.value)}
                    placeholder={t('searchLang')}
                    className={styles.controlMenuSearch}
                  />
                  <div className={styles.controlMenuList}>
                    {filteredLangs.map(item => (
                      <button
                        type="button"
                        key={item.code}
                        onClick={() => { setLanguage(item.code); setLangOpen(false) }}
                        className={`${styles.controlMenuItem} ${language === item.code ? styles.controlMenuItemActive : ''}`}
                      >
                        {item.code === 'auto'
                          ? t('autoLang')
                          : item.label === item.name
                            ? item.label
                            : `${item.label} — ${item.name}`}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="relative">
              <button
                type="button"
                onClick={() => { setSlidesOpen(!slidesOpen); setLangOpen(false) }}
                className={styles.controlButton}
              >
                <Icon name="chart" className={`w-4 h-4 ${styles.controlButtonIcon}`} />
                {getSlideCountParam() === 'auto' ? t('autoSlides') : t('slidesCount', { n: getSlideCountParam() })}
                <span>⌄</span>
              </button>
              {slidesOpen && (
                <div className={`${styles.controlMenu} ${styles.controlMenuNarrow}`}>
                  <input
                    type="number"
                    min={3}
                    max={MAX_NUMBER_OF_SLIDES}
                    value={customSlides}
                    onChange={e => { setCustomSlides(e.target.value); setSlideCount('custom') }}
                    placeholder={t('customSlidesPlaceholder')}
                    className={styles.controlMenuSearch}
                    style={{ width: 'calc(100% - 8px)', margin: 4 }}
                  />
                  <button
                    type="button"
                    onClick={() => { setSlideCount('auto'); setCustomSlides(''); setSlidesOpen(false) }}
                    className={styles.controlMenuItem}
                  >
                    {t('autoOption')}
                  </button>
                  {SLIDE_OPTIONS.map(n => (
                    <button
                      type="button"
                      key={n}
                      onClick={() => { setSlideCount(n); setSlidesOpen(false) }}
                      className={`${styles.controlMenuItem} ${slideCount === n ? styles.controlMenuItemActive : ''}`}
                    >
                      {t('slidesCount', { n })}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <input ref={fileInputRef} type="file" accept=".pdf,.md,.txt" className="hidden" onChange={e => { setFile(e.target.files ? e.target.files[0] : null); if (promptError) setPromptError(false) }} />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className={styles.controlButton}
              title={t('pdfUploadTitle')}
            >
              <Icon name="paperclip" className={`w-4 h-4 ${styles.controlButtonIcon}`} />
              <span className="truncate">{file ? file.name : t('pdfUpload')}</span>
              {file && (
                <span
                  role="button"
                  tabIndex={0}
                  onClick={e => { e.stopPropagation(); setFile(null) }}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      e.stopPropagation()
                      setFile(null)
                    }
                  }}
                >
                  <Icon name="x" className="w-4 h-4" />
                </span>
              )}
            </button>
            <div className={styles.controlSpacer} />
            <button
              type="button"
              onClick={handleGenerate}
              disabled={!canGenerate || isStarting}
              aria-busy={isStarting}
              className={`${styles.primaryButton} ${isStarting ? styles.primaryButtonBusy : ''}`}
              title={selectedTemplate ? selectedTemplate.title : undefined}
            >
              <Icon name="sparkles" className="w-4 h-4" />
              <span className={styles.primaryButtonLabel}>
                {isStarting ? t('starting') : t('generateBtn')}
              </span>
              <Icon name="arrowRight" className="w-4 h-4" />
            </button>
          </div>
        </section>
      </div>
      <div className={styles.buildStrip} aria-label={t('workflowLabel')}>
        <div className={styles.buildStripItem}><span className={styles.buildStripNumber}>01</span><div><strong>{t('direction')}</strong><span>{t('directionHint')}</span></div></div>
        <div className={styles.buildStripItem}><span className={styles.buildStripNumber}>02</span><div><strong>{t('source')}</strong><span>{t('sourceHint')}</span></div></div>
        <div className={styles.buildStripItem}><span className={styles.buildStripNumber}>03</span><div><strong>{t('structure')}</strong><span>{t('structureHint')}</span></div></div>
      </div>

      <section className={styles.gallery}>
        <div className={styles.galleryHeader}>
          <div><h2 className={styles.galleryTitle}>{t('orTemplates')}</h2><p className={styles.galleryMeta}>{filteredTemplates.length} {t('curatedStartingPoints')}</p></div>
          <div className={styles.galleryTools}>
            <input className={styles.search} value={templateQuery} onChange={e => setTemplateQuery(e.target.value)} placeholder={t('searchTemplates')} aria-label={t('searchTemplates')} />
            <button type="button" onClick={() => setTemplateStyle('all')} className={`${styles.filter} ${templateStyle === 'all' ? styles.filterActive : ''}`}>{t('allTemplates')}</button>
            {templateStyles.map(style => <button type="button" key={style} onClick={() => setTemplateStyle(style)} className={`${styles.filter} ${templateStyle === style ? styles.filterActive : ''}`}>{templateStyleLabel(style)}</button>)}
          </div>
        </div>
        {filteredTemplates.length > 0 ? <div className={styles.templateGrid}>{filteredTemplates.map(tpl => {
          const isSelected = selectedTemplate?.id === tpl.id
          return (
          <article
            key={tpl.id}
            aria-disabled={!tpl.available}
            aria-pressed={isSelected}
            onClick={() => { if (!isStarting && tpl.available) handleSelectTemplate(tpl.id, tpl.color || '#000', tpl.title) }}
            className={`${styles.templateCard}${isSelected ? ` ${styles.templateCardSelected}` : ''}`}
            style={!tpl.available ? { opacity: 0.55, cursor: 'not-allowed' } : undefined}
          >
          <div className={styles.templateCover} style={{ backgroundColor: tpl.color || '#333' }}>
            {tpl.cover ? (
              // Same-origin /api rewrite sends session cookies; browser HTTP cache applies.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`/api/templates/${tpl.id}/cover${tpl.cover_version ? `?v=${tpl.cover_version}` : ''}`}
                alt=""
                loading="lazy"
                decoding="async"
              />
            ) : null}
          </div>
          <div className={styles.templateInfo}>
            <h3 className={styles.templateName}>{tpl.title}</h3>
            <p className={styles.templateDescription}>{tpl.unavailable_reason || tpl.description}</p>
            <div className={styles.templateMeta}>
              <span className={styles.templateTag}>{isSelected ? t('selectedTemplate') : (tpl.available ? (tpl.style ? templateStyleLabel(tpl.style) : t('templateLabel')) : 'Legacy')}</span>
              <button
                type="button"
                className={styles.previewButton}
                onClick={event => { event.stopPropagation(); openTemplatePreview(tpl) }}
              >
                <Icon name="eye" className="w-4 h-4" />
                {t('previewTemplate')}
              </button>
            </div>
          </div>
        </article>
          )
        })}</div> : <div className={styles.emptyGallery}>{t('noTemplatesMatch')}</div>}
      </section>

      {preview && (
        <SlideLightbox
          apiUrl={API_URL}
          eyebrow={preview.title}
          ariaLabel={preview.title}
          index={previewIndex}
          total={previewSlides.length}
          slideUrl={
            previewSlides[previewIndex]
              ? `/api/templates/${preview.id}/slides/${encodeURIComponent(previewSlides[previewIndex])}`
              : null
          }
          slideAlt={previewSlides[previewIndex] || preview.title}
          hint={t('slidePreviewHint')}
          placeholder={previewLoading ? t('previewLoading') : t('previewEmpty')}
          onClose={closeTemplatePreview}
          onPrev={() => setPreviewIndex(index => Math.max(0, index - 1))}
          onNext={() =>
            setPreviewIndex(index => Math.min(Math.max(previewSlides.length - 1, 0), index + 1))
          }
          closeLabel={t('closePreview')}
          previousLabel={t('previousSlide')}
          nextLabel={t('nextSlide')}
          action={
            preview.available ? (
              <button
                type="button"
                className={lightboxStyles.slideLightboxAction}
                disabled={isStarting}
                onClick={() => {
                  setSelectedTemplate({ id: preview.id, color: preview.color, title: preview.title })
                  closeTemplatePreview()
                }}
              >
                <Icon name="sparkles" className="w-4 h-4" />
                <span>{t('useTemplate')}</span>
              </button>
            ) : undefined
          }
        />
      )}
    </div>
  )
}
