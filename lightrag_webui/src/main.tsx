import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import AppRouter from './AppRouter'
import { useAuthStore } from '@/stores/state'
import './i18n.ts';
import 'katex/dist/katex.min.css';
// Import KaTeX extensions at app startup to ensure they are registered before any rendering
import 'katex/contrib/mhchem'; // Chemistry formulas: \ce{} and \pu{}
import 'katex/contrib/copy-tex'; // Allow copying rendered formulas as LaTeX source

// Magic-link login: a Telegram team owner opens `…/webui/?token=<jwt>` (a query
// param, since the app uses a HashRouter). Consume it before render so the app
// shows authenticated, then strip it from the URL.
const _magicParams = new URLSearchParams(window.location.search)
const _magicToken = _magicParams.get('token')
if (_magicToken) {
  useAuthStore.getState().login(_magicToken)
  _magicParams.delete('token')
  const _search = _magicParams.toString()
  window.history.replaceState(
    {},
    '',
    window.location.pathname + (_search ? `?${_search}` : '') + window.location.hash
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppRouter />
  </StrictMode>
)
