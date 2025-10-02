"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ThemeButton } from "@/features/ThemeButton/ui/ThemeButton";
import Image from "next/image";
import { Eye, EyeClosed } from "lucide-react";

const API_LOGIN = `${process.env.NEXT_PUBLIC_API_URL || ""}/login`;

export function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr("");
    if (!email || !pass) {
      setErr("Введите почту и пароль");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(API_LOGIN, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include", // вдруг сервер ставит httpOnly cookie token
        body: JSON.stringify({ email, password: pass }),
      });

      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error("Ошибка входа");
      }

      // Вариант 1: сервер вернул токен в JSON (если не httpOnly)
      try {
        const data = await res.clone().json();
        if (data?.token) {
          document.cookie = `token=${data.token}; Path=/; SameSite=Lax`;
        }
      } catch {
        // игнор: возможно только cookie httpOnly
      }

      router.replace("/dashboards/feedback-impact"); // стартовая страница после входа
    } catch (e: any) {
      setErr(e.message || "Ошибка входа");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col w-full gap-24">
      <header className="flex items-center justify-between px-16 pt-10 h-20 w-full">
        <div className="flex items-center gap-3">
          {/*Вставь сюда логотип gpb_logo.svg из public*/}
          <Image
            src="/gpb_logo.svg"
            alt="Газпромбанк"
            width={40}
            height={40}
            priority
            className="h-10 w-10"
          />
          <span className="font-bold text-2xl text-gray-800 dark:text-gray-100">
            Газпромбанк
          </span>
        </div>
        <ThemeButton variant="text" showTargetLabel={false} />
      </header>

      <main className="flex-1 flex items-start justify-center">
        <form
          onSubmit={onSubmit}
          className="w-full max-w-md bg-white dark:bg-[#1B1C1F] rounded-2xl border border-gray-200 dark:border-[#2a2a2a] p-10 shadow-sm flex flex-col gap-6"
        >
          <h1 className="text-2xl font-semibold text-center">Добрый день!</h1>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
              Почта
            </label>
            <input
              type="email"
              autoComplete="email"
              placeholder="mail@mail.ru"
              className="w-full rounded-md bg-[#F3F5F8] dark:bg-[#25272B] border border-transparent focus:border-blue-500 focus:bg-white dark:focus:bg-[#2d2f33] px-4 py-2 text-sm outline-none transition"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
              Пароль
            </label>
            <div className="relative">
              <input
                type={showPass ? "text" : "password"}
                autoComplete="current-password"
                placeholder="Ваш пароль"
                className="w-full rounded-md bg-[#F3F5F8] dark:bg-[#25272B] border border-transparent focus:border-blue-500 focus:bg-white dark:focus:bg-[#2d2f33] px-4 py-2 pr-10 text-sm outline-none transition"
                value={pass}
                onChange={(e) => setPass(e.target.value)}
                required
                minLength={8}
              />
              <button
                type="button"
                onClick={() => setShowPass((v) => !v)}
                className="absolute inset-y-0 right-2 px-1 flex items-center text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                tabIndex={-1}
                aria-label={showPass ? "Скрыть пароль" : "Показать пароль"}
              >
                {showPass ? <Eye size={16} /> : <EyeClosed size={16} />}
              </button>
            </div>
            <p className="text-[11px] text-gray-500 dark:text-gray-500 leading-snug">
              Это должна быть комбинация минимум из 8 букв, цифр и символов.
            </p>
          </div>

          {err && (
            <div className="text-xs text-red-500 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded px-3 py-2">
              {err}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-2 h-11 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium transition shadow-sm"
          >
            {loading ? "Входим..." : "Войти"}
          </button>
        </form>
      </main>
    </div>
  );
}
