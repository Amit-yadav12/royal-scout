import Image from "next/image";
import { cn } from "@/lib/cn";

/** Royal Scout's original vector crest; works on the deep-navy command shell. */
export function BrandMark({ className, title = "Royal Scout" }: { className?: string; title?: string }) {
  return (
    <Image
      src="/royal-scout-compact.svg"
      alt={title}
      className={cn("shrink-0 object-contain", className)}
      width={120}
      height={130}
      sizes="(max-width: 640px) 34px, 44px"
      priority
      unoptimized
    />
  );
}

export function BrandLockup({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <BrandMark className={compact ? "h-9 w-9" : "h-11 w-11"} />
      {!compact ? (
        <span className="leading-tight">
          <span className="block font-serif text-sm font-bold tracking-[0.17em] text-white">ROYAL SCOUT</span>
          <span className="mt-1 block text-[0.56rem] font-semibold tracking-[0.19em] text-gold-300 uppercase">Cricket scouting intelligence</span>
        </span>
      ) : null}
    </span>
  );
}
