import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <App />
    </div>
  </StrictMode>,
)
