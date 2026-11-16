import * as React from "react";
import { cn } from "@/lib/cn";

export function DataTable({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full min-w-full border-collapse text-left text-xs">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return (
    <thead className="sticky top-0 z-10 bg-surface-muted/95 backdrop-blur">
      <tr className="border-b border-surface-line">{children}</tr>
    </thead>
  );
}

export function TH({
  children,
  align = "left",
  className,
  title,
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  title?: string;
}) {
  return (
    <th
      title={title}
      scope="col"
      className={cn(
        "px-2.5 py-2 text-2xs font-semibold tracking-[0.06em] whitespace-nowrap text-ink-faint uppercase",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-surface-line/80">{children}</tbody>;
}

export function TD({
  children,
  align = "left",
  className,
  mono = false,
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  mono?: boolean;
}) {
  return (
    <td
      className={cn(
        "px-2.5 py-2 align-middle whitespace-nowrap",
        align === "right" && "text-right",
        align === "center" && "text-center",
        mono && "font-mono tabular-nums",
        className,
      )}
    >
      {children}
    </td>
  );
}
