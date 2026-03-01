/** Tiny utility to merge Tailwind class strings. No clsx/twMerge dependency. */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}
