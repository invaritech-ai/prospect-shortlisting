import type { ComponentType } from 'react'
import type { CSSProperties } from 'react'
import type { LucideProps } from 'lucide-react'
import {
  Activity,
  Building2,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Download,
  Eye,
  ExternalLink,
  Gauge,
  Globe,
  RefreshCw,
  Settings,
  SlidersHorizontal,
  Upload,
  Users,
  Workflow,
  X,
} from 'lucide-react'

type IconProps = { className?: string; size?: number; style?: CSSProperties }

function withLucide(Component: ComponentType<LucideProps>) {
  return function Icon({ className = '', size = 20, style }: IconProps) {
    return <Component className={className} size={size} style={style} strokeWidth={1.8} />
  }
}

export const IconBuilding = withLucide(Building2)
export const IconGlobe = withLucide(Globe)
export const IconChart = withLucide(Gauge)
export const IconTimeline = withLucide(Activity)
export const IconPulse = withLucide(Activity)
export const IconSliders = withLucide(SlidersHorizontal)
export const IconCog = withLucide(Settings)
export const IconUpload = withLucide(Upload)
export const IconX = withLucide(X)
export const IconChevronLeft = withLucide(ChevronLeft)
export const IconChevronRight = withLucide(ChevronRight)
export const IconChevronDown = withLucide(ChevronDown)
export const IconRefresh = withLucide(RefreshCw)
export const IconCheck = withLucide(Check)
export const IconDownload = withLucide(Download)
export const IconEye = withLucide(Eye)
export const IconExternalLink = withLucide(ExternalLink)
export const IconUsers = withLucide(Users)
export const IconWorkflow = withLucide(Workflow)
