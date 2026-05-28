import type { ComponentType } from 'react'
import type { CSSProperties } from 'react'
import type { LucideProps } from 'lucide-react'
import {
  Activity,
  ArrowLeft,
  Building2,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  CircleEllipsis,
  Clock3,
  Copy,
  Download,
  Eye,
  ExternalLink,
  Gauge,
  Globe,
  History,
  Plus,
  Pencil,
  RefreshCw,
  Settings,
  SlidersHorizontal,
  ThumbsDown,
  ThumbsUp,
  Upload,
  Users,
  Workflow,
  X,
  Zap,
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
export const IconDots = withLucide(CircleEllipsis)
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
export const IconCopy = withLucide(Copy)
export const IconZap = withLucide(Zap)
export const IconEye = withLucide(Eye)
export const IconPencil = withLucide(Pencil)
export const IconPlus = withLucide(Plus)
export const IconArrowLeft = withLucide(ArrowLeft)
export const IconThumbUp = withLucide(ThumbsUp)
export const IconThumbDown = withLucide(ThumbsDown)
export const IconExternalLink = withLucide(ExternalLink)
export const IconHistory = withLucide(History)
export const IconUsers = withLucide(Users)
export const IconClock = withLucide(Clock3)
export const IconWorkflow = withLucide(Workflow)
