"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ComponentType, HTMLAttributes } from "react";

interface NavButtonProps extends HTMLAttributes<HTMLAnchorElement> {
  href: string;
  label: string;
  icon?: ComponentType<{ className?: string }>;
  active?: boolean;
}

export function NavButton({
  href,
  label,
  icon: Icon,
  active,
  className = "",
  ...rest
}: NavButtonProps) {
  const pathname = usePathname();

  const computedActive =
    active !== undefined
      ? active
      : (pathname ?? "") === href || (pathname ?? "").startsWith(href + "/");

  return (
    <Link
      href={href}
      className={`flex flex-row items-center w-full h-fit gap-2.5 px-2.5 py-3 rounded-2xl transition-colors
        hover:bg-[#F5F5F5] dark:hover:bg-[#1B1C1F] ${
          computedActive ? "text-[#0F62FE]" : "text-[#1A1A1A] dark:text-white "
        } ${className}`}
      {...rest}
    >
      {Icon && <Icon className="w-5 h-5 shrink-0" />}
      <span>{label}</span>
    </Link>
  );
}
