import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { GaugeIcon } from 'lucide-react'
import Button from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/Dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/Select'
import {
  getUsage,
  getAdminQuotas,
  setWorkspaceTier,
  type QuotaUsage
} from '@/api/lightrag'
import { useAuthStore } from '@/stores/state'

const MB = 1024 * 1024

function fmtMB(bytes: number): string {
  return `${(bytes / MB).toFixed(bytes >= MB ? 0 : 1)} MB`
}

/** Compact "S: used/limit · Q: used/limit" indicator for the active workspace. */
function pair(used: number, limit: number | null, unit: (n: number) => string): string {
  return limit == null ? `${unit(used)} / ∞` : `${unit(used)} / ${unit(limit)}`
}

/** Inline usage indicator shown for non-guest sessions. */
export function UsageIndicator() {
  const { t } = useTranslation()
  const { isGuestMode, activeWorkspace } = useAuthStore()
  const [usage, setUsage] = useState<QuotaUsage | null>(null)

  useEffect(() => {
    if (isGuestMode) return
    let cancelled = false
    getUsage()
      .then((u) => {
        if (!cancelled) setUsage(u)
      })
      .catch(() => {
        /* usage is best-effort; ignore errors (e.g. quotas disabled) */
      })
    return () => {
      cancelled = true
    }
  }, [isGuestMode, activeWorkspace])

  if (isGuestMode || !usage) return null

  return (
    <span
      className="text-xs text-gray-500 dark:text-gray-400 cursor-default"
      title={t('quota.indicatorTooltip', 'Team resource usage (storage / monthly enquiries)')}
    >
      {usage.tier} · {pair(usage.storage.used_bytes, usage.storage.limit_bytes, fmtMB)} ·{' '}
      {pair(usage.enquiries.used, usage.enquiries.limit, (n) => String(n))} q
    </span>
  )
}

/** Admin-only panel: list workspaces with usage and assign tiers. */
export function QuotaAdminPanel() {
  const { t } = useTranslation()
  const { role } = useAuthStore()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<QuotaUsage[]>([])
  const [tiers, setTiers] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    getAdminQuotas()
      .then((d) => {
        setRows(d.workspaces)
        setTiers(d.tiers)
      })
      .finally(() => setLoading(false))
  }, [])

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) load()
  }

  const onTierChange = async (workspace: string, tier: string) => {
    await setWorkspaceTier(workspace, tier)
    load()
  }

  if (role !== 'admin') return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          side="bottom"
          tooltip={t('quota.manageTooltip', 'Manage team tiers & quotas')}
        >
          <GaugeIcon className="size-4" aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('quota.title', 'Team resource quotas')}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-1 pr-2">{t('quota.workspace', 'Workspace')}</th>
                <th className="py-1 pr-2">{t('quota.tier', 'Tier')}</th>
                <th className="py-1 pr-2">{t('quota.storage', 'Storage')}</th>
                <th className="py-1 pr-2">{t('quota.docs', 'Docs')}</th>
                <th className="py-1 pr-2">{t('quota.enquiries', 'Enquiries (mo)')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.workspace} className="border-t border-border/40">
                  <td className="py-1 pr-2 font-mono">{r.workspace}</td>
                  <td className="py-1 pr-2">
                    <Select value={r.tier} onValueChange={(v) => onTierChange(r.workspace, v)}>
                      <SelectTrigger className="h-7 w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {tiers.map((tier) => (
                          <SelectItem key={tier} value={tier}>
                            {tier}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="py-1 pr-2">
                    {pair(r.storage.used_bytes, r.storage.limit_bytes, fmtMB)}
                  </td>
                  <td className="py-1 pr-2">
                    {pair(r.storage.doc_count, r.storage.doc_limit, (n) => String(n))}
                  </td>
                  <td className="py-1 pr-2">
                    {pair(r.enquiries.used, r.enquiries.limit, (n) => String(n))}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-3 text-center text-gray-500">
                    {loading ? t('quota.loading', 'Loading…') : t('quota.empty', 'No team workspaces yet')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </DialogContent>
    </Dialog>
  )
}
