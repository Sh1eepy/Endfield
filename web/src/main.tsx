import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/layout.css'
import './styles/components.css'
import './styles/tree.css'
import './styles/ask.css'
import './styles/kb.css'
import './styles/operator.css'
import './styles/entry.css'
import './styles/responsive.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
