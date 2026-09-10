const STORAGE_KEY = 'bpmflow-appearance'

export type AppearancePreference = 'light' | 'dark' | 'system'

const LIGHT_THEME = 'corporate'
const DARK_THEME = 'business'

export function getStoredAppearance(): AppearancePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
    /* ignore */
  }
  return 'light'
}

function resolveTheme(preference: AppearancePreference): string {
  if (preference === 'light') return LIGHT_THEME
  if (preference === 'dark') return DARK_THEME
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  return prefersDark ? DARK_THEME : LIGHT_THEME
}

export function applyAppearance(preference: AppearancePreference): void {
  const theme = resolveTheme(preference)
  document.documentElement.setAttribute('data-theme', theme)
}

export function setAppearancePreference(preference: AppearancePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, preference)
  } catch {
    /* ignore */
  }
  applyAppearance(preference)
}

export function initAppearance(): void {
  applyAppearance(getStoredAppearance())

  if (typeof window === 'undefined' || !window.matchMedia) return
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const onChange = () => {
    if (getStoredAppearance() === 'system') applyAppearance('system')
  }
  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', onChange)
  } else if (typeof media.addListener === 'function') {
    media.addListener(onChange)
  }
}
