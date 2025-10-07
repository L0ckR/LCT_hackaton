"use client";

import dynamic from "next/dynamic";
import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { ChevronDown } from "lucide-react";
import data from "@/shared/api/business_impact_dashboard.json";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

/* ---------- Dark mode hook ---------- */
function useDarkMode() {
  const [isDark, setIsDark] = useState<boolean>(() =>
    typeof document !== "undefined"
      ? document.documentElement.classList.contains("dark")
      : false
  );
  useEffect(() => {
    if (typeof document === "undefined") return;
    const update = () =>
      setIsDark(document.documentElement.classList.contains("dark"));
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    const handler = () => update();
    window.addEventListener("theme-change", handler);
    return () => {
      mo.disconnect();
      window.removeEventListener("theme-change", handler);
    };
  }, []);
  return isDark;
}

/* ---------- Helpers ---------- */
const releaseChart = data.charts.find(
  (c: any) => c.id === "product_release_timeline"
);
const sentimentChart = data.charts.find(
  (c: any) => c.id === "mobile_app_sentiment_trend"
);

function buildReleaseOption(
  release: any,
  start: string,
  end: string,
  isDark: boolean
) {
  if (!release) return {};
  const events = release.events || [];
  const xAxis = release.xAxis;
  const dateToMonth = (d: string) => d.slice(0, 7);
  const monthIndex: Record<string, number> = {};
  xAxis.forEach((m: string, i: number) => (monthIndex[m] = i));

  const scatterData = events
    .map((ev: any) => {
      const m = dateToMonth(ev.date);
      if (monthIndex[m] === undefined) return null;
      return {
        name: ev.name,
        value: monthIndex[m],
        originalDate: ev.date,
        category: ev.category,
        hypothesis: ev.hypothesis,
        observed: ev.observed,
      };
    })
    .filter(Boolean);

  const textColor = isDark ? "#E5E7EB" : "#374151";
  const axisColor = isDark ? "#9CA3AF" : "#4B5563";
  const tooltipBg = isDark ? "#1F2937" : "#FFFFFF";
  const tooltipBorder = isDark ? "#374151" : "#E5E7EB";

  return {
    backgroundColor: "transparent",
    title: {
      text: release.title,
      left: 0,
      top: 0,
      textStyle: { fontSize: 14, fontWeight: 600, color: textColor },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: tooltipBg,
      borderColor: tooltipBorder,
      textStyle: { color: textColor },
      formatter: (p: any) => {
        const d = p.data;
        const obs = d.observed;
        return `<b>${d.name}</b><br/>Дата: ${d.originalDate}<br/>Категория: ${d.category}<br/>Гипотеза: ${d.hypothesis}<br/>ΔNPS: ${obs.nps_delta}<br/>+Позитив: ${obs.positive_uplift_pct}%<br/>ΔНег доля: ${obs.negative_share_delta_pct}%`;
      },
    },
    grid: { left: 100, right: 50, top: 60, bottom: 20 },
    xAxis: {
      type: "category",
      data: xAxis,
      boundaryGap: true,
      axisLabel: { rotate: 0, color: axisColor },
      axisLine: { lineStyle: { color: axisColor } },
      axisTick: { lineStyle: { color: axisColor } },
    },
    yAxis: { type: "value", max: 1, min: 0, show: false },
    series: [
      {
        type: "scatter",
        symbol: "circle",
        symbolSize: 26,
        data: scatterData,
        itemStyle: {
          color: (p: any) => {
            const cat = p.data.category;
            if (cat === "feature") return "#1976d2";
            if (cat === "performance") return "#7b61ff";
            if (cat === "stability") return "#ef5350";
            if (cat === "support") return "#ffa726";
            if (cat === "ux") return "#26c6da";
            return "#9e9e9e";
          },
          shadowBlur: 6,
          shadowColor: isDark ? "rgba(0,0,0,0.5)" : "rgba(0,0,0,0.2)",
        },
        label: {
          show: true,
          position: "top",
          formatter: (p: any) => p.data.name,
          fontSize: 10,
          lineHeight: 11,
          color: textColor,
        },
      },
    ],
  };
}

function buildSentimentOption(sent: any, releases: any[], isDark: boolean) {
  if (!sent) return {};
  const xAxis = sent.xAxis;
  const seriesDef = sent.series || [];
  const textColor = isDark ? "#E5E7EB" : "#374151";
  const axisColor = isDark ? "#9CA3AF" : "#4B5563";
  const gridLine = isDark ? "#2f3338" : "#E5E7EB";
  const tooltipBg = isDark ? "#1F2937" : "#FFFFFF";
  const tooltipBorder = isDark ? "#374151" : "#E5E7EB";

  const markLines = (releases || []).map((r) => ({
    xAxis: r.date.slice(0, 7),
    label: {
      formatter: r.label,
      color: axisColor,
      fontSize: 10,
    },
    lineStyle: {
      type:
        r.impact === "high"
          ? "solid"
          : r.impact === "moderate"
          ? "dashed"
          : "dotted",
      color:
        r.impact === "high"
          ? "#ef5350"
          : r.impact === "moderate"
          ? "#ffa726"
          : "#1976d2",
      width: r.impact === "high" ? 2 : 1,
    },
  }));

  return {
    backgroundColor: "transparent",
    title: {
      text: sent.title,
      left: 0,
      top: 0,
      textStyle: { fontSize: 14, fontWeight: 600, color: textColor },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: tooltipBg,
      borderColor: tooltipBorder,
      textStyle: { color: textColor },
      formatter: (p: any[]) => {
        let out = `<b>${p[0].axisValue}</b><br/>`;
        p.forEach((pt) => {
          out += `${pt.marker} ${pt.seriesName}: <b>${pt.data}</b><br/>`;
        });
        return out;
      },
    },
    legend: {
      top: 28,
      textStyle: { color: textColor },
    },
    grid: { left: 80, right: 20, top: 90, bottom: 40 },
    xAxis: {
      type: "category",
      data: xAxis,
      axisTick: { alignWithLabel: true, lineStyle: { color: axisColor } },
      axisLabel: { color: axisColor },
      axisLine: { lineStyle: { color: axisColor } },
    },
    yAxis: {
      type: "value",
      name: sent.yAxisLabel,
      nameGap: 32,
      axisLabel: { color: axisColor },
      axisLine: { lineStyle: { color: axisColor } },
      splitLine: { show: true, lineStyle: { color: gridLine } },
    },
    series: seriesDef.map((s: any, i: number) => ({
      name: s.name,
      type: "line",
      stack: s.stack,
      smooth: true,
      areaStyle: { opacity: 0.35 },
      lineStyle: { width: 2 },
      emphasis: { focus: "series" },
      data: s.data,
      color: ["#34c759", "#9e9e9e", "#ff6b6b"][i] || undefined,
    })),
    markLine: {
      symbol: "none",
      label: { rotate: 90, distance: 6 },
      data: markLines,
    },
  };
}

/* ---------- Product Picker (модалка) ---------- */
interface ProductPickerProps {
  all: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  onClose: () => void;
}

function ProductPicker({
  all,
  selected,
  onChange,
  onClose,
}: ProductPickerProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  const toggle = (p: string) => {
    if (p === "Все") {
      onChange(["Все"]);
      return;
    }
    const base = selected.filter((s) => s !== "Все");
    if (base.includes(p)) {
      const next = base.filter((s) => s !== p);
      onChange(next.length ? next : ["Все"]);
    } else {
      onChange([...base, p]);
    }
  };

  const isChecked = (p: string) =>
    selected.includes("Все") ? p === "Все" : selected.includes(p);

  const onEsc = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );
  const outside = useCallback(
    (e: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener("keydown", onEsc);
    document.addEventListener("mousedown", outside);
    return () => {
      document.removeEventListener("keydown", onEsc);
      document.removeEventListener("mousedown", outside);
    };
  }, [onEsc, outside]);

  const sorted = [...all].sort((a, b) =>
    a === "Все" ? -1 : b === "Все" ? 1 : a.localeCompare(b, "ru")
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 bg-black/35 backdrop-blur-sm">
      <div
        ref={ref}
        className="w-full max-w-md rounded-xl border bg-white dark:bg-[#1B1C1F] dark:border-[#2a2a2a] shadow-xl flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between h-12 px-5 border-b dark:border-[#2a2a2a]">
          <h3 className="font-semibold text-sm">Выбор продуктов</h3>
          <button
            onClick={onClose}
            className="text-xs px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-[#2a2a2a]"
          >
            ✕
          </button>
        </div>
        <div className="px-5 py-3 max-h-[50vh] overflow-auto flex flex-col gap-2">
          {sorted.map((p) => (
            <label
              key={p}
              className="flex items-center gap-2 text-sm cursor-pointer select-none"
            >
              <input
                type="checkbox"
                className="accent-[#1976d2]"
                checked={isChecked(p)}
                onChange={() => toggle(p)}
              />
              <span className={p === "Все" ? "font-medium" : ""}>{p}</span>
              {p === "Все" && selected.includes("Все") && (
                <span className="ml-auto text-[10px] uppercase tracking-wide text-gray-400">
                  все
                </span>
              )}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-3 px-5 py-3 border-t dark:border-[#2a2a2a]">
          <button
            onClick={() => onChange(["Все"])}
            className="text-xs px-3 py-2 rounded border border-gray-300 dark:border-[#3a3a3a] hover:bg-gray-100 dark:hover:bg-[#2a2a2a]"
          >
            Сброс
          </button>
          <button
            onClick={onClose}
            className="ml-auto text-xs px-4 py-2 rounded bg-[#1976d2] text-white hover:bg-[#1664b1]"
          >
            Готово
          </button>
        </div>
      </div>
    </div>
  );
}

export function FeedbackDashboard() {
  const isDark = useDarkMode();
  const [dateStart, setDateStart] = useState(data.timeframe.start);
  const [dateEnd, setDateEnd] = useState(data.timeframe.end);

  // ---------- NEW product filter state ----------
  const allProductsRaw: string[] = data.filters?.products || [];
  const allProducts = allProductsRaw.includes("Все")
    ? allProductsRaw
    : ["Все", ...allProductsRaw];
  const [selectedProducts, setSelectedProducts] = useState<string[]>(["Все"]);
  const [pickerOpen, setPickerOpen] = useState(false);

  const productsLabel = selectedProducts.includes("Все")
    ? "Все продукты"
    : `Выбрано: ${selectedProducts.length}`;

  // ---------- (Optional) aggregation placeholder ----------
  // NOTE: Расчет по продуктам не реализован, т.к. в JSON нет помесячных productSeries.
  // Если появится структура вида sentimentChart.productSeries[product] = { series: [...] },
  // добавить агрегацию аналогично TonalityDashboard.

  const months = sentimentChart?.xAxis || [];
  const filteredMonths = useMemo(
    () =>
      months.filter(
        (m: string) => m >= dateStart.slice(0, 7) && m <= dateEnd.slice(0, 7)
      ),
    [months, dateStart, dateEnd]
  );

  const filteredSentiment = useMemo(() => {
    if (!sentimentChart) return null;
    const idx = months
      .map((m: string, i: number) => ({ m, i }))
      .filter(({ m }) => filteredMonths.includes(m))
      .map(({ i }) => i);
    return {
      ...sentimentChart,
      xAxis: filteredMonths,
      series: (sentimentChart.series ?? []).map((s: any) => ({
        ...s,
        data: idx.map((i: number) => s.data[i]),
      })),
    };
  }, [sentimentChart, filteredMonths, months]);

  const filteredReleases = useMemo(() => {
    const all = sentimentChart?.annotations?.releases || [];
    if (!filteredMonths.length) return [];
    return all.filter(
      (r: any) =>
        r.date.slice(0, 7) >= filteredMonths[0] &&
        r.date.slice(0, 7) <= filteredMonths[filteredMonths.length - 1]
    );
  }, [sentimentChart, filteredMonths]);

  const releaseOption = useMemo(
    () => buildReleaseOption(releaseChart, dateStart, dateEnd, isDark),
    [releaseChart, dateStart, dateEnd, isDark]
  );
  const sentimentOption = useMemo(
    () => buildSentimentOption(filteredSentiment, filteredReleases, isDark),
    [filteredSentiment, filteredReleases, isDark]
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{data.title}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 w-full">
          Стратегический взгляд: привязка релизов к изменению структуры
          тональности.
        </p>
      </header>

      {/* Filters */}
      <section className="flex flex-row flex-wrap gap-6">
        {/* NEW Product Filter Button */}
        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            Продукты
          </label>
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="flex items-center justify-between gap-2 font-medium text-sm px-4 py-2 min-w-[220px] border-t border-[#DDE1E6] bg-white dark:bg-[#1B1C1F] rounded cursor-pointer hover:bg-gray-50 dark:hover:bg-[#242529] transition-colors"
          >
            <span>{productsLabel}</span>
            <ChevronDown
              size={16}
              className={`opacity-60 transition-transform ${
                pickerOpen ? "rotate-180" : ""
              }`}
            />
          </button>
        </div>

        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            От
          </label>
          <input
            type="date"
            className="rounded font-medium text-sm px-4 py-2 min-w-[200px] border-t border-[#DDE1E6] bg-white dark:bg-[#1B1C1F]"
            value={dateStart}
            min={data.timeframe.start}
            max={data.timeframe.end}
            onChange={(e) => setDateStart(e.target.value)}
          />
        </div>
        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            До
          </label>
          <input
            type="date"
            className="rounded font-medium text-sm px-4 py-2 min-w-[200px] border-t border-[#DDE1E6] bg-white dark:bg-[#1B1C1F]"
            value={dateEnd}
            min={data.timeframe.start}
            max={data.timeframe.end}
            onChange={(e) => setDateEnd(e.target.value)}
          />
        </div>
      </section>

      {/* High-level KPIs */}
      <section className="grid grid-cols-6 gap-2">
        {[
          {
            label: "NPS мобильного приложения (текущий)",
            k: "current_mobile_app_nps",
            fmt: (v: number) => v.toFixed(1),
          },
          {
            label: "Базовый NPS (Jan 2024)",
            k: "baseline_mobile_app_nps_jan2024",
            fmt: (v: number) => v.toFixed(1),
          },
          {
            label: "Δ NPS (абс.)",
            k: "delta_nps_absolute",
            fmt: (v: number) => "+" + v.toFixed(1),
          },
          {
            label: "Снижение доли негатива (п.п.)",
            k: "cumulative_negative_share_reduction_pct",
            fmt: (v: number) => v.toFixed(1),
          },
          {
            label: "Рост позитива (посл. 3м, %)",
            k: "latest_3m_positive_growth_pct",
            fmt: (v: number) => v.toFixed(1) + "%",
          },
          {
            label: "Средний uplift после релизов (%)",
            k: "avg_post_release_positive_uplift_pct",
            fmt: (v: number) => v.toFixed(1) + "%",
          },
        ].map((m) => (
          <div
            key={m.k}
            className="flex flex-col bg-white dark:bg-[#1B1C1F] dark:border-[#2a2a2a] justify-between"
          >
            <span className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {m.label}
            </span>
            <span className="text-xl font-semibold mt-1">
              {m.fmt((data.metrics as any)[m.k])}
            </span>
          </div>
        ))}
      </section>

      {/* Charts */}
      <section className="flex flex-col gap-8">
        <div className="flex flex-col gap-3">
          <div className="h-[17vh] bg-white dark:bg-[#1B1C1F] dark:border-[#2a2a2a]">
            <ReactECharts
              key={`releases-${isDark ? "dark" : "light"}`}
              option={{
                ...releaseOption,
                xAxis: {
                  ...(releaseOption as any).xAxis,
                  data: filteredMonths,
                },
                series: (releaseOption as any).series?.map((s: any) => ({
                  ...s,
                  data: s.data?.filter((d: any) =>
                    filteredMonths.includes(d.originalDate.slice(0, 7))
                  ),
                })),
              }}
              notMerge
              lazyUpdate
              style={{ width: "100%", height: "100%" }}
            />
          </div>
          <div className="h-[30vh] bg-white dark:bg-[#1B1C1F] dark:border-[#2a2a2a]">
            <ReactECharts
              key={`sentiment-${isDark ? "dark" : "light"}`}
              option={{
                ...sentimentOption,
                xAxis: {
                  ...(sentimentOption as any).xAxis,
                  data: filteredMonths,
                },
              }}
              notMerge
              lazyUpdate
              style={{ width: "100%", height: "100%" }}
            />
          </div>
        </div>
      </section>

      {pickerOpen && (
        <ProductPicker
          all={allProducts}
          selected={selectedProducts}
          onChange={setSelectedProducts}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  );
}
