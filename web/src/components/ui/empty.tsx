import { AlertTriangle, Info, Inbox } from "lucide-react";
import { cn } from "@/lib/cn";

export function EmptyState({
  title,
  description,
  tone = "info",
  action,
}: {
  title: string;
  description: React.ReactNode;
  tone?: "info" | "warning" | "empty";
  action?: React.ReactNode;
}) {
  const Icon = tone === "warning" ? AlertTriangle : tone === "empty" ? Inbox : Info;
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border px-4 py-4",
        tone === "warning" ? "border-amber-200 bg-amber-50/60" : "border-surface-line bg-surface-muted",
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone === "warning" ? "text-amber-700" : "text-ink-faint")} />
      <div className="text-xs leading-relaxed">
        <p className="font-semibold text-ink">{title}</p>
        <div className="mt-0.5 text-ink-soft">{description}</div>
        {action ? <div className="mt-2">{action}</div> : null}
      </div>
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warning" | "success" | "danger" }) {
  return (
    <p
      className={cn(
        "rounded border px-2.5 py-1.5 text-2xs leading-relaxed",
        tone === "warning"
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : tone === "success"
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : tone === "danger"
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-surface-line bg-surface-muted text-ink-soft",
      )}
    >
      {children}
    </p>
  );
}
