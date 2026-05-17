import type { DragEvent, FormEvent } from 'react'
import { IconUpload } from '../../ui/icons'

interface UploadZoneProps {
  file: File | null
  isUploading: boolean
  isDragActive: boolean
  onSetFile: (f: File | null) => void
  onSetIsDragActive: (v: boolean) => void
  onUpload: (e: FormEvent) => void
}

export function UploadZone({ file, isUploading, isDragActive, onSetFile, onSetIsDragActive, onUpload }: UploadZoneProps) {
  const handleDragOver  = (e: DragEvent) => { e.preventDefault(); onSetIsDragActive(true) }
  const handleDragLeave = () => onSetIsDragActive(false)
  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    onSetIsDragActive(false)
    const f = e.dataTransfer.files[0]
    if (f) onSetFile(f)
  }

  return (
    <section>
      <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Add More Companies</p>
      <form onSubmit={onUpload} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={isDragActive ? 'oc-upload-zone oc-upload-zone-active' : 'oc-upload-zone'}
        >
          <IconUpload size={24} className="oc-icon-muted" />
          <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0, textAlign: 'center' }}>
            {file
              ? <><strong style={{ color: 'var(--oc-text)', fontWeight: 600 }}>{file.name}</strong> — ready to upload</>
              : 'Drop a CSV, TXT, XLS, or XLSX file here'}
          </p>
          <input type="file" accept=".csv,.txt,.xls,.xlsx" className="hidden" id="csv-upload"
            onChange={(e) => onSetFile(e.target.files?.[0] ?? null)} />
          <label htmlFor="csv-upload" className="oc-upload-file-label">Browse files</label>
        </div>
        {file && (
          <button type="submit" disabled={isUploading} className="oc-btn oc-btn-primary oc-btn-md">
            {isUploading ? 'Uploading…' : `Upload ${file.name}`}
          </button>
        )}
      </form>
    </section>
  )
}
