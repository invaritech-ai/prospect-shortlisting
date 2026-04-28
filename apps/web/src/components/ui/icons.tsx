// Minimal inline SVG icons — 20×20 viewBox, currentColor stroke

type IconProps = { className?: string; size?: number }

export function IconBuilding({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="2" y="3" width="16" height="14" rx="1.5" />
      <path d="M6 7h2M6 10h2M12 7h2M12 10h2M8 17v-4h4v4" />
    </svg>
  )
}

export function IconGlobe({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="10" cy="10" r="8" />
      <path d="M2 10h16M10 2a14 14 0 0 1 0 16M10 2a14 14 0 0 0 0 16" />
    </svg>
  )
}

export function IconChart({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="2" y="11" width="4" height="7" rx="1" />
      <rect x="8" y="6" width="4" height="12" rx="1" />
      <rect x="14" y="2" width="4" height="16" rx="1" />
    </svg>
  )
}

export function IconTimeline({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 5h4M13 5h4M3 10h8M15 10h2M3 15h6M12 15h8" />
      <circle cx="10.5" cy="5" r="1.4" />
      <circle cx="13" cy="10" r="1.4" />
      <circle cx="9.5" cy="15" r="1.4" />
    </svg>
  )
}

export function IconPulse({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M2 10h3l2-4 3 8 2-4h6" />
      <path d="M2 4v12" opacity="0.4" />
    </svg>
  )
}

export function IconDots({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="currentColor" className={className}>
      <circle cx="5" cy="10" r="1.6" />
      <circle cx="10" cy="10" r="1.6" />
      <circle cx="15" cy="10" r="1.6" />
    </svg>
  )
}

export function IconSliders({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 5h14M3 10h14M3 15h14" />
      <circle cx="7" cy="5" r="2" fill="white" />
      <circle cx="13" cy="10" r="2" fill="white" />
      <circle cx="8" cy="15" r="2" fill="white" />
    </svg>
  )
}

export function IconCog({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="10" cy="10" r="2.8" />
      <path d="M10 2.6v2M10 15.4v2M17.4 10h-2M4.6 10h-2M15.2 4.8l-1.4 1.4M6.2 13.8l-1.4 1.4M15.2 15.2l-1.4-1.4M6.2 6.2L4.8 4.8" />
      <circle cx="10" cy="10" r="6.2" opacity="0.45" />
    </svg>
  )
}

export function IconUpload({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M10 13V4M6 8l4-4 4 4" />
      <path d="M3 14v2a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2" />
    </svg>
  )
}

export function IconX({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className={className}>
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  )
}

export function IconChevronLeft({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M13 15l-5-5 5-5" />
    </svg>
  )
}

export function IconChevronRight({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M7 5l5 5-5 5" />
    </svg>
  )
}

export function IconRefresh({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 10a7 7 0 1 0 1.5-4.5" />
      <path d="M3 5v5h5" />
    </svg>
  )
}

export function IconCheck({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4 10l5 5 7-7" />
    </svg>
  )
}

export function IconDownload({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M10 4v9M6 10l4 4 4-4" />
      <path d="M3 14v2a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2" />
    </svg>
  )
}

export function IconCopy({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
      <path d="M13 7V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h3" />
    </svg>
  )
}

export function IconZap({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M11 2L3 11h7l-1 7 8-9h-7l1-7z" />
    </svg>
  )
}

export function IconEye({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6z" />
      <circle cx="10" cy="10" r="2.5" />
    </svg>
  )
}

export function IconPencil({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M13 3l4 4-9 9H4v-4l9-9z" />
    </svg>
  )
}

export function IconPlus({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className={className}>
      <path d="M10 4v12M4 10h12" />
    </svg>
  )
}

export function IconArrowLeft({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M15 10H5M9 6l-4 4 4 4" />
    </svg>
  )
}

export function IconThumbUp({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M7 9l3-6a2 2 0 0 1 2 2v3h4a1 1 0 0 1 1 1.1l-1 5a1 1 0 0 1-1 .9H7V9z" />
      <rect x="3" y="9" width="4" height="8" rx="1" />
    </svg>
  )
}

export function IconThumbDown({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M13 11l-3 6a2 2 0 0 1-2-2v-3H4a1 1 0 0 1-1-1.1l1-5A1 1 0 0 1 5 5h8v6z" />
      <rect x="13" y="3" width="4" height="8" rx="1" />
    </svg>
  )
}

export function IconExternalLink({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M11 3h6v6M17 3l-8 8M8 5H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-4" />
    </svg>
  )
}

export function IconHistory({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 10a7 7 0 1 0 7-7 7 7 0 0 0-5 2.1L3 7"/>
      <path d="M3 3v4h4"/>
      <path d="M10 6v4l3 2"/>
    </svg>
  )
}

export function IconUsers({ className = '', size = 20 }: IconProps) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M13 11c2.2.3 4 1.7 4 3.5V16H3v-1.5C3 12.7 4.8 11.3 7 11"/>
      <circle cx="10" cy="6" r="3"/>
      <path d="M15.5 9.5c1.5.4 2.5 1.5 2.5 3V14M4.5 9.5C3 9.9 2 11 2 12.5V14"/>
      <circle cx="15" cy="5" r="2"/>
      <circle cx="5" cy="5" r="2"/>
    </svg>
  )
}
