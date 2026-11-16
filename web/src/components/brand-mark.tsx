import { useId } from "react";
import { cn } from "@/lib/cn";

/** Original Royal Scout emblem: interlocking initials inside a precision ring with a ball-seam accent. */
export function BrandMark({ className, title = "Royal Scout" }: { className?: string; title?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg aria-label={title} className={cn("shrink-0", className)} viewBox="0 0 64 64" fill="none" role="img" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`${id}-bg`} x1="8" y1="4" x2="57" y2="60" gradientUnits="userSpaceOnUse">
          <stop stopColor="#17294C" /><stop offset="1" stopColor="#080E1D" />
        </linearGradient>
        <linearGradient id={`${id}-metal`} x1="16" y1="13" x2="49" y2="51" gradientUnits="userSpaceOnUse">
          <stop stopColor="#F0D8A1" /><stop offset="1" stopColor="#C9A45C" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="17" fill={`url(#${id}-bg)`} />
      <rect x="3" y="3" width="58" height="58" rx="16" stroke="white" strokeOpacity=".09" />
      <circle cx="32" cy="32" r="22.25" stroke={`url(#${id}-metal)`} strokeOpacity=".72" strokeWidth="1.2" />
      <circle cx="32" cy="32" r="18.5" stroke="white" strokeOpacity=".1" strokeWidth=".8" />
      <path d="M21 43V21h9.4c5.3 0 8.4 2.6 8.4 7 0 3.4-1.9 5.7-5.3 6.6L41 43h-6.2l-6.6-7.9h-2.1V43H21Zm5.1-12.1h4.1c2.4 0 3.6-1 3.6-2.8s-1.2-2.8-3.6-2.8h-4.1v5.6Z" fill="#F7F8FA" />
      <path d="M45 24.4c-1.7-2.3-4.2-3.5-7.3-3.5-4.7 0-7.7 2.5-7.7 6.1 0 3.3 2.2 4.8 6.6 5.7l2.1.5c2.1.5 2.9 1 2.9 2 0 1.1-1.2 1.8-3.3 1.8-2.4 0-4.5-.9-6.2-2.6l-3.1 3.2c2.1 2.4 5.4 3.7 9.2 3.7 5.1 0 8.4-2.5 8.4-6.4 0-3.3-2.1-5-6.7-5.9l-2.2-.5c-2.1-.4-2.9-.9-2.9-1.9 0-1 .9-1.6 2.8-1.6 1.7 0 3.2.6 4.4 1.7l3-2.3Z" fill="#D72D79" />
      <path d="M47.8 12.7c-4.1 4.5-6.3 9.6-6.6 15.2m9.1-12.8c-4.2 4.1-6.8 8.9-7.6 14.3" stroke={`url(#${id}-metal)`} strokeWidth="1.25" strokeLinecap="round" opacity=".9" />
      <circle cx="48.6" cy="12.5" r="1.2" fill="#D72D79" />
    </svg>
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
