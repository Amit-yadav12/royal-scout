import Image from "next/image";
import { cn } from "@/lib/cn";

/** Premium Royal Scout monogram, rendered from the selected optimized emblem artwork. */
export function BrandMark({ className, title = "Royal Scout" }: { className?: string; title?: string }) {
  return (
    <Image
      src="/royal-scout-mark.webp"
      alt={title}
      aria-label={title}
      className={cn("shrink-0 rounded-xl object-cover", className)}
      width={768}
      height={768}
      sizes="(max-width: 640px) 32px, 40px"
      priority
    />
  );
}

export function BrandLockup({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <BrandMark className={compact ? "h-8 w-8" : "h-10 w-10"} />
      {!compact ? <span className="leading-tight">
        <span className="block text-xs font-bold tracking-[0.16em] text-white">ROYAL SCOUT</span>
        <span className="mt-0.5 block text-[0.58rem] font-medium tracking-[0.2em] text-white/45 uppercase">Intelligence OS</span>
      </span> : null}
    </span>
  );
}
