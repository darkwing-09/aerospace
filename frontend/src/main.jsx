import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

import { pdfjs } from 'react-pdf'

// Set worker from local node_modules (Vite handles the path)
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
