"use client";

import { useEffect, useState, useCallback } from "react";
import { Moon, Sun } from "lucide-react";

interface ThemeButtonProps {
  variant?: "text" | "nav";
  className?: string;
  showTargetLabel?: boolean;
}

export function ThemeButton({
  variant = "nav",
  className = "",
  showTargetLabel = true,
}: ThemeButtonProps) {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  const apply = useCallback((t: "light" | "dark") => {
    document.documentElement.classList.toggle("dark", t === "dark");
    localStorage.setItem("theme", t);
  }, []);

  useEffect(() => {
    const saved =
      (localStorage.getItem("theme") as "light" | "dark" | null) || undefined;
    const initial =
      saved ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light");
    setTheme(initial);
    apply(initial);
  }, [apply]);

  const toggle = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    apply(next);
  };

  const target = theme === "light" ? "dark" : "light";

  const labelCurrent = theme === "dark" ? "Тёмная тема" : "Светлая тема";
  const labelTarget = target === "dark" ? "Тёмная тема" : "Светлая тема";

  const label = showTargetLabel ? labelTarget : labelCurrent;
  const icon = target === "dark" ? <Sun /> : <Moon />;

  if (variant === "text") {
    return (
      <button
        type="button"
        onClick={toggle}
        className={`cursor-pointer flex flex-row items-center h-fit gap-2.5 px-2.5 py-3 rounded-2xl transition-colors text-[#1A1A1A] dark:text-white`}
      >
        {label}
        {icon}
      </button>
    );
  }

  return (
    <button
      className={`cursor-pointer flex flex-row items-center w-full h-fit gap-2.5 px-2.5 py-3 rounded-2xl transition-colors
        hover:bg-[#F5F5F5] dark:hover:bg-[#1B1C1F] active:text-[#0F62FE] text-[#1A1A1A] dark:text-white`}
      onClick={toggle}
      type="button"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
