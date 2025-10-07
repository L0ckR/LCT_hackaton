"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { ChevronDown } from "lucide-react";
import incidentData from "@/shared/api/incident_dashboard.json";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Добавляем отслеживание смены темы
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

/* ---------------- Helpers ---------------- */
function parseISO(d: string) {
  return new Date(d);
}
function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), max);
}
function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}
function hexToRgb(hex: string) {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}
function rgbToHex({ r, g, b }: { r: number; g: number; b: number }) {
  const h = (n: number) => n.toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}
function interpolateColor(
  v: number,
  min: number,
  max: number,
  bad: string,
  good: string,
  neutral: string
) {
  if (v === 0) return neutral;
  const cl = clamp(v, min, max);
  if (cl === 0) return neutral;
  if (cl > 0) {
    const t = cl / (max || 1);
    const from = hexToRgb(neutral);
    const to = hexToRgb(bad);
    return rgbToHex({
      r: Math.round(lerp(from.r, to.r, t)),
      g: Math.round(lerp(from.g, to.g, t)),
      b: Math.round(lerp(from.b, to.b, t)),
    });
  } else {
    const t = Math.abs(cl) / Math.abs(min || 1);
    const from = hexToRgb(neutral);
    const to = hexToRgb(good);
    return rgbToHex({
      r: Math.round(lerp(from.r, to.r, t)),
      g: Math.round(lerp(from.g, to.g, t)),
      b: Math.round(lerp(from.b, to.b, t)),
    });
  }
}

/* ---------------- Data Extraction ---------------- */
const treemapRaw = incidentData.charts.find(
  (c: any) => c.id === "problems_treemap"
);
const funnelRaw = incidentData.charts.find((c: any) => c.id === "sla_funnel");
const sparkRaw = incidentData.charts.find(
  (c: any) => c.id === "top5_negative_topics"
);
const allProducts = incidentData.filters.products || [];

/* ---------------- Chart Builders ---------------- */
function buildTreemapOption(
  rootData: any,
  productFilter: string[],
  colorScale: any,
  isDark: boolean
) {
  if (!rootData) return {};
  const { min, max, badColor, goodColor, neutralColor } = {
    min: colorScale.scale.min,
    max: colorScale.scale.max,
    badColor: colorScale.scale.badColor,
    goodColor: colorScale.scale.goodColor,
    neutralColor: colorScale.scale.neutralColor,
  };
  const textColor = isDark ? "#E5E7EB" : "#374151";
  const borderColLv0 = isDark ? "#3a3a3a" : "#fff";
  const borderColLv1 = isDark ? "#555" : "#eee";

  const useAll = productFilter.length === 0;
  const filteredChildren = (rootData.data || []).filter((n: any) =>
    useAll ? true : productFilter.includes(n.name)
  );
  const mapNode = (n: any) => ({
    name: n.name,
    value: n.value,
    delta_pct: n.delta_pct,
    direction: n.direction,
    itemStyle: {
      color: interpolateColor(
        n.delta_pct,
        min,
        max,
        badColor,
        goodColor,
        neutralColor
      ),
      borderColor: isDark ? "#1B1C1F" : "#ffffff",
      borderWidth: 1,
    },
    children: (n.children || []).map(mapNode),
  });

  return {
    backgroundColor: "transparent",
    tooltip: {
      confine: true,
      textStyle: { color: textColor },
      backgroundColor: isDark ? "#1F2937" : "#ffffff",
      borderColor: isDark ? "#374151" : "#E5E7EB",
      formatter: (info: any) => {
        const d = info.data;
        if (!d) return "";
        const arrow = d.delta_pct > 0 ? "▲" : d.delta_pct < 0 ? "▼" : "•";
        return `<b>${d.name}</b><br/>Объем: ${d.value}<br/>Δ: ${d.delta_pct}% ${arrow}`;
      },
    },
    series: [
      {
        type: "treemap",
        roam: true,
        nodeClick: "zoomToNode",
        breadcrumb: {
          show: true,
          itemStyle: {
            color: isDark ? "#2d2f33" : "#f5f5f5",
            textStyle: { color: textColor },
          },
        },
        upperLabel: {
          show: true,
          height: 24,
          color: textColor,
          backgroundColor: isDark ? "rgba(0,0,0,0.35)" : "rgba(0,0,0,0.15)",
        },
        label: {
          show: true,
          formatter: "{b}",
          color: textColor,
        },
        levels: [
          {
            itemStyle: {
              borderColor: borderColLv0,
              borderWidth: 2,
              gapWidth: 3,
            },
          },
          { itemStyle: { borderColor: borderColLv1, gapWidth: 2 } },
        ],
        data: filteredChildren.map(mapNode),
      },
    ],
  };
}

function buildFunnelOption(funnel: any, isDark: boolean) {
  if (!funnel) return {};
  const stageData = funnel.data || [];
  const textColor = isDark ? "#E5E7EB" : "#374151";
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      confine: true,
      textStyle: { color: textColor },
      backgroundColor: isDark ? "#1F2937" : "#ffffff",
      borderColor: isDark ? "#374151" : "#E5E7EB",
      formatter: (p: any) => {
        const item = stageData[p.dataIndex];
        const conv =
          item.conversion_pct_from_prev != null
            ? `<br/>Конверсия: ${item.conversion_pct_from_prev}%`
            : "";
        return `<b>${item.stage}</b><br/>${item.value}${conv}`;
      },
    },
    legend: {
      show: false,
      textStyle: { color: textColor },
    },
    series: [
      {
        type: "funnel",
        left: "5%",
        top: 20,
        bottom: 20,
        width: "80%",
        minSize: "10%",
        maxSize: "90%",
        sort: "none",
        gap: 2,
        label: {
          show: true,
          color: textColor,
          formatter: (p: any) => {
            const item = stageData[p.dataIndex];
            const c = item.conversion_pct_from_prev;
            return c
              ? `${item.stage}\n${item.value} (${c}%)`
              : `${item.stage}\n${item.value}`;
          },
        },
        labelLine: { length: 10, lineStyle: { width: 1, color: textColor } },
        itemStyle: {
          borderColor: isDark ? "#1B1C1F" : "#fff",
          borderWidth: 1,
        },
        data: stageData.map((s: any, i: number) => ({
          name: s.stage,
          value: s.value,
          itemStyle: {
            color: ["#1976d2", "#42a5f5", "#66bb6a", "#ffa726", "#ef5350"][
              i % 5
            ],
          },
        })),
      },
    ],
  };
}

function buildSparkOption(item: any, color: string, isDark: boolean) {
  const axisColor = isDark ? "#9CA3AF" : "#6B7280";
  return {
    grid: { left: 4, right: 4, top: 8, bottom: 4 },
    xAxis: {
      type: "category",
      data: item.series.map((_: any, i: number) => i),
      show: false,
      axisLabel: { color: axisColor },
    },
    yAxis: { type: "value", show: false },
    tooltip: {
      trigger: "axis",
      backgroundColor: isDark ? "#1F2937" : "#ffffff",
      borderColor: isDark ? "#374151" : "#E5E7EB",
      textStyle: { color: isDark ? "#E5E7EB" : "#374151" },
      formatter: (p: any) => {
        const i = p[0].dataIndex;
        return `${item.topic}<br/>Неделя #${i + 1}: ${item.series[i]}`;
      },
    },
    series: [
      {
        type: "line",
        data: item.series,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color },
        areaStyle: { color: color + "22" },
      },
    ],
  };
}

/* ---------- Product Picker (popup like TonalityDashboard) ---------- */
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

  const closeOnEsc = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  const handleOutside = useCallback(
    (e: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener("keydown", closeOnEsc);
    document.addEventListener("mousedown", handleOutside);
    return () => {
      document.removeEventListener("keydown", closeOnEsc);
      document.removeEventListener("mousedown", handleOutside);
    };
  }, [closeOnEsc, handleOutside]);

  const sorted = [...all].sort((a, b) =>
    a === "Все" ? -1 : b === "Все" ? 1 : a.localeCompare(b, "ru")
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/35 backdrop-blur-sm p-4">
      <div
        ref={ref}
        className="w-full max-w-md rounded-xl border bg-white dark:bg-[#1B1C1F] dark:border-[#2a2a2a] shadow-xl overflow-hidden flex flex-col"
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
              className="flex items-center gap-2 text-sm cursor-pointer"
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

/* ---------------- Component ---------------- */
export function IncidentDashboard() {
  // REPLACED single product with multi-select
  // const [product, setProduct] = useState<string>("Все");
  const [selectedProducts, setSelectedProducts] = useState<string[]>(["Все"]);
  const [pickerOpen, setPickerOpen] = useState(false);

  const [dateStart, setDateStart] = useState(incidentData.timeframe.start);
  const [dateEnd, setDateEnd] = useState(incidentData.timeframe.end);
  const isDark = useDarkMode();

  // Spark filtering with multi products
  const sparkItems = sparkRaw?.items || [];
  const sparkXAxis = sparkRaw?.xAxis || [];
  const filteredSpark = useMemo(() => {
    const s = parseISO(dateStart);
    const e = parseISO(dateEnd);
    const indices = sparkXAxis
      .map((d: string, idx: number) => ({ idx, date: parseISO(d) }))
      .filter(({ date }) => date >= s && date <= e)
      .map(({ idx }) => idx);

    const useAll = selectedProducts.includes("Все");
    return sparkItems
      .filter((it: any) =>
        useAll ? true : selectedProducts.includes(it.product)
      )
      .map((it: any) => ({
        ...it,
        series: indices.map((i) => it.series[i]),
        last_value: it.series[indices[indices.length - 1]],
      }));
  }, [sparkItems, sparkXAxis, dateStart, dateEnd, selectedProducts]);

  // Treemap option with multi products
  const treemapOption = useMemo(
    () =>
      buildTreemapOption(
        treemapRaw,
        selectedProducts.includes("Все") ? [] : selectedProducts,
        treemapRaw?.colorEncoding || {
          scale: {
            min: -40,
            max: 60,
            badColor: "#d32f2f",
            goodColor: "#2e7d32",
            neutralColor: "#9e9e9e",
          },
        },
        isDark
      ),
    [treemapRaw, selectedProducts, isDark]
  );

  // Funnel unchanged (global)
  const funnelOption = useMemo(
    () => buildFunnelOption(funnelRaw, isDark),
    [funnelRaw, isDark]
  );

  const sparkPalette = ["#1976d2", "#ef5350", "#34c759", "#ffa726", "#7b61ff"];

  useEffect(() => {
    if (new Date(dateStart) > new Date(dateEnd)) setDateEnd(dateStart);
  }, [dateStart, dateEnd]);

  const productsLabel = selectedProducts.includes("Все")
    ? "Все продукты"
    : `Выбрано: ${selectedProducts.length}`;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{incidentData.title}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Тактический дашборд: фокус на оперативное выявление и обработку
          инцидентов / негативных тем.
        </p>
      </header>

      {/* Filters (каналы убраны, продукт + даты в требуемом стиле) */}
      <section className="flex flex-row flex-wrap gap-6">
        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            Продукты
          </label>
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="flex items-center justify-between gap-2 font-medium text-sm px-4 py-2 min-w-[220px] border-t border-[#DDE1E6] bg-white dark:bg-[#1B1C1F] rounded hover:bg-gray-50 dark:hover:bg-[#242529] transition-colors"
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

        {/* Dates remain */}
        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            От
          </label>
          <input
            type="date"
            className="rounded font-medium text-sm px-4 py-2 min-w-[200px] border-t border-[#DDE1E6] bg-white dark:bg-[#1B1C1F]"
            value={dateStart}
            min={incidentData.timeframe.start}
            max={incidentData.timeframe.end}
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
            min={incidentData.timeframe.start}
            max={incidentData.timeframe.end}
            onChange={(e) => setDateEnd(e.target.value)}
          />
        </div>
      </section>

      {/* KPI summary */}
      <section className="grid grid-cols-5 gap-2">
        {[
          {
            k: "total_negative_reviews",
            label: "Негативные отзывы",
            fmt: (v: any) => v.toLocaleString("ru-RU"),
          },
          {
            k: "avg_resolution_time_hours",
            label: "Среднее время решения (ч)",
            fmt: (v: any) => v.toFixed(1),
          },
          {
            k: "median_resolution_time_hours",
            label: "Медиана времени (ч)",
            fmt: (v: any) => v,
          },
          {
            k: "sla_met_pct",
            label: "SLA выполнено (%)",
            fmt: (v: any) => v + "%",
          },
          {
            k: "reopened_pct",
            label: "Повторно открыто (%)",
            fmt: (v: any) => v + "%",
          },
        ].map((m) => (
          <div key={m.k} className="flex flex-col bg-white dark:bg-[#1B1C1F]">
            <span className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {m.label}
            </span>
            <span className="text-xl font-semibold mt-1">
              {m.fmt((incidentData.metrics as any)[m.k])}
            </span>
          </div>
        ))}
      </section>

      {/* Main charts */}
      <section className="grid grid-cols-12">
        <div className="col-span-7 flex flex-col">
          <h2 className="font-medium">Актуальные проблемные области</h2>
          <div className="h-[200px] bg-white dark:bg-[#1B1C1F]">
            <ReactECharts
              key={`treemap-${isDark ? "dark" : "light"}`}
              option={treemapOption}
              style={{ height: "100%", width: "100%" }}
              notMerge
              lazyUpdate
            />
          </div>
        </div>
        <div className="col-span-5 flex flex-col">
          <h2 className="font-medium">Процесс обработки (SLA воронка)</h2>
          <div className="h-[200px] bg-white dark:bg-[#1B1C1F]">
            <ReactECharts
              key={`funnel-${isDark ? "dark" : "light"}`}
              option={funnelOption}
              style={{ height: "100%", width: "100%" }}
              notMerge
              lazyUpdate
            />
          </div>
        </div>
      </section>

      {/* Sparklines */}
      <section className="flex flex-col">
        <h2 className="font-medium">TOP-5 негативных тем (динамика)</h2>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {filteredSpark.map((it: any, idx: number) => {
            const arrow =
              it.direction === "up" ? "▲" : it.direction === "down" ? "▼" : "•";
            const arrowColor =
              it.direction === "up"
                ? "text-red-500"
                : it.direction === "down"
                ? "text-green-600"
                : "text-gray-500";
            return (
              <div
                key={it.id}
                className="flex flex-col bg-white dark:bg-[#1B1C1F]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-col">
                    <span className="text-xs font-medium">{it.product}</span>
                    <span className="text-[11px] text-gray-500 line-clamp-1">
                      {it.topic}
                    </span>
                  </div>
                  <div
                    className={`text-xs font-semibold ${arrowColor} flex flex-col items-end`}
                  >
                    <span>
                      {arrow} {it.change_abs}
                    </span>
                    <span className="text-[10px] text-gray-400">
                      {it.change_pct}%
                    </span>
                  </div>
                </div>
                <div className="h-16">
                  <ReactECharts
                    key={`${it.id}-${isDark ? "dark" : "light"}`}
                    option={buildSparkOption(
                      it,
                      sparkPalette[idx % sparkPalette.length],
                      isDark
                    )}
                    style={{ height: "100%", width: "100%" }}
                    notMerge
                    lazyUpdate
                  />
                </div>
              </div>
            );
          })}
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
