import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/* ---------------- Card ---------------- */
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...p }, ref) => (
  <div ref={ref} className={cn("rounded-xl border bg-card text-card-foreground shadow-sm", className)} {...p} />
));
Card.displayName = "Card";
export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col space-y-1 p-5 pb-3", className)} {...p} />
);
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("font-semibold leading-none tracking-tight", className)} {...p} />
);
export const CardDescription = ({ className, ...p }: React.HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("text-sm text-muted-foreground", className)} {...p} />
);
export const CardContent = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-5 pt-0", className)} {...p} />
);

/* ---------------- Badge ---------------- */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        success: "border-transparent bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
        warning: "border-transparent bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
        danger: "border-transparent bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
        info: "border-transparent bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
        violet: "border-transparent bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
      },
    },
    defaultVariants: { variant: "default" },
  },
);
export function Badge({
  className,
  variant,
  ...p
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...p} />;
}

/* ---------------- Inputs ---------------- */
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        className,
      )}
      {...p}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...p}
    />
  ),
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...p }, ref) => (
    <select
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...p}
    />
  ),
);
Select.displayName = "Select";

export const Label = ({ className, ...p }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label className={cn("text-sm font-medium leading-none", className)} {...p} />
);

/* ---------------- Table ---------------- */
export const Table = ({ className, ...p }: React.HTMLAttributes<HTMLTableElement>) => (
  <div className="relative w-full overflow-auto">
    <table className={cn("w-full caption-bottom text-sm", className)} {...p} />
  </div>
);
export const THead = ({ className, ...p }: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <thead className={cn("bg-muted/50 [&_tr]:border-b", className)} {...p} />
);
export const TBody = ({ className, ...p }: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <tbody className={cn("[&_tr:last-child]:border-0", className)} {...p} />
);
export const TR = ({ className, ...p }: React.HTMLAttributes<HTMLTableRowElement>) => (
  <tr className={cn("border-b transition-colors hover:bg-muted/40", className)} {...p} />
);
export const TH = ({ className, ...p }: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th
    className={cn("h-10 px-3 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground", className)}
    {...p}
  />
);
export const TD = ({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) => (
  <td className={cn("px-3 py-2.5 align-middle", className)} {...p} />
);

/* ---------------- Misc ---------------- */
export const Skeleton = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("animate-pulse rounded-md bg-muted", className)} {...p} />
);
