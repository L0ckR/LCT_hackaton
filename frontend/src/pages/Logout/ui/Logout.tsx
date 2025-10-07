"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const API_LOGOUT = `${process.env.NEXT_PUBLIC_API_URL || ""}/logout`;

export function Logout() {
  const router = useRouter();
  const once = useRef(false);

  useEffect(() => {
    if (once.current) return;
    once.current = true;

    const doLogout = async () => {
      try {
        // Один GET запрос на logout
        await fetch(API_LOGOUT, {
          method: "GET",
          credentials: "include",
          cache: "no-store",
        });
      } catch {
        // игнорируем ошибки — все равно чистим токен и редиректим
      }

      // Удаляем cookie token (если не httpOnly)
      document.cookie =
        "token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";

      // (опционально) чистим local/session storage
      try {
        localStorage.removeItem("token");
        sessionStorage.removeItem("token");
      } catch {}

      // Редирект
      router.replace("/login");
    };

    doLogout();
  }, [router]);

  return (
    <div className="flex items-center justify-center h-screen text-sm text-gray-500 dark:text-gray-400">
      Выход...
    </div>
  );
}
