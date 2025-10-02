"use client";

import { NavButton } from "@/features/NavButton";
import { ThemeButton } from "@/features/ThemeButton";
import {
  ChartNoAxesCombined,
  ChartSpline,
  FolderPlus,
  LogOut,
  SquareKanban,
} from "lucide-react";

export function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex flex-row gap-4 px-24 py-10 h-screen w-screen">
      <aside className="flex flex-col w-80 p-2.5 rounded-3xl justify-between">
        <nav className="flex flex-col w-full h-max gap-2.5">
          <NavButton
            href="/dashboards/tonality"
            label="Тональность"
            icon={ChartNoAxesCombined}
          />
          <NavButton
            href="/dashboards/incident-response"
            label="Инцидент-реагирование"
            icon={SquareKanban}
          />
          <NavButton
            href="/dashboards/feedback-impact"
            label="Влияние отзывов"
            icon={ChartSpline}
          />
        </nav>
        <div className="flex flex-col w-full h-max gap-2.5 border-t dark:border-[#DDE1E6] border-[#26262620] pt-2.5">
          <ThemeButton variant="nav" showTargetLabel={false} />
          <NavButton href="/logout" label="Выход" icon={LogOut} />
        </div>
      </aside>
      <main className="flex py-5 px-7 flex-col border dark:bg-[#1B1C1F] bg-[#FFFFFF] border-[#26262620] rounded-3xl w-full h-full overflow-y-scroll no-scrollbar overflow-x-visible">
        {children}
      </main>
    </div>
  );
}
