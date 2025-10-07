"use client";

import dynamic from "next/dynamic";
import data from "@/shared/api/data.json";
import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { ChevronDown } from "lucide-react";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Base charts from data
const baseVolumeChart = data.charts.find(
  (c: any) => c.id === "volume_nps_trend"
);
const baseSentimentChart = data.charts.find(
  (c: any) => c.id === "sentiment_stacked_trend"
);
const baseHeatmapChart = data.charts.find(
  (c: any) => c.id === "heatmap_problem_topics"
);

const palette = ["#1976d2", "#ff6b6b", "#34c759", "#ffa726", "#7b61ff"];

/* ---------------- Helpers ---------------- */
function parseMonth(monthStr: string) {
  const [y, m] = monthStr.split("-").map(Number);
  return new Date(y, m - 1, 1);
}

function filterByDate(c: any, start: string, end: string) {
  if (!c) return c;
  const s = parseMonth(start);
  const e = parseMonth(end);
  const indices = (c.xAxis as string[])
    .map((d, i) => ({ i, d: parseMonth(d) }))
    .filter(({ d }) => d >= s && d <= e)
    .map(({ i }) => i);
  return {
    ...c,
    xAxis: indices.map((i) => c.xAxis[i]),
    series: (c.series || []).map((srs: any) => ({
      ...srs,
      data: indices.map((i) => srs.data[i]),
    })),
  };
}

function filterHeatmapByDate(chart: any, start: string, end: string) {
  if (!chart) return chart;
  if (!chart.xAxis || !chart.data) return chart;
  const s = parseMonth(start);
  const e = parseMonth(end);
  const indices = (chart.xAxis as string[])
    .map((d, i) => ({ i, d: parseMonth(d) }))
    .filter(({ d }) => d >= s && d <= e)
    .map(({ i }) => i);
  return {
    ...chart,
    xAxis: indices.map((i) => chart.xAxis[i]),
    data: (chart.data as number[][]).map((row) => indices.map((i) => row[i])),
  };
}

function buildOptionVolumeNps(c: any, isDark: boolean) {
  if (!c) return {};
  const legendColor = isDark ? "#E5E7EB" : "#374151";
  const axisColor = isDark ? "#9CA3AF" : "#4B5563";
  return {
    grid: { left: 90, right: 90, top: 30, bottom: 30 },
    tooltip: { trigger: "axis" },
    legend: { top: 0, textStyle: { color: legendColor } },
    xAxis: { type: "category", data: c.xAxis, axisLabel: { color: axisColor } },
    yAxis: [
      {
        type: "value",
        name: c.yAxisLeftLabel,
        axisLabel: { color: axisColor },
      },
      {
        type: "value",
        name: c.yAxisRightLabel,
        axisLabel: { color: axisColor },
      },
    ],
    series: [
      { ...c.series[0], type: "bar", itemStyle: { color: palette[0] } },
      {
        ...c.series[1],
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        lineStyle: { width: 2, color: palette[1] },
      },
    ],
  };
}

function buildOptionSentiment(c: any, isDark: boolean) {
  if (!c) return {};
  const legendColor = isDark ? "#E5E7EB" : "#374151";
  const axisColor = isDark ? "#9CA3AF" : "#4B5563";
  const positive = (c.series || []).find((s: any) => /Позитив/i.test(s.name));
  const neutral = (c.series || []).find((s: any) => /Нейтрал/i.test(s.name));
  const negative = (c.series || []).find((s: any) => /Негатив/i.test(s.name));
  const ordered = [negative, neutral, positive].filter(Boolean);
  const colorByName: Record<string, string> = {
    Позитивные: "#34c759",
    Нейтральные: "#9e9e9e",
    Негативные: "#ff6b6b",
  };
  return {
    tooltip: { trigger: "axis" },
    legend: {
      top: 0,
      data: ["Позитивные", "Нейтральные", "Негативные"],
      textStyle: { color: legendColor },
    },
    grid: { left: 60, right: 40, top: 50, bottom: 20 },
    xAxis: { type: "category", data: c.xAxis, axisLabel: { color: axisColor } },
    yAxis: {
      type: "value",
      name: c.yAxisLabel,
      axisLabel: { color: axisColor },
    },
    series: ordered.map((s: any) => ({
      name: s.name,
      type: "line",
      stack: "sentiment",
      areaStyle: {},
      showSymbol: false,
      lineStyle: { width: 1.5, color: colorByName[s.name] || undefined },
      itemStyle: { color: colorByName[s.name] || undefined },
      data: s.data,
    })),
  };
}

function buildOptionHeatmap(c: any) {
  if (!c) return {};
  const xCats: string[] = c.xAxis || [];
  const yCats: string[] = c.yAxis || [];
  const matrix: number[][] = c.data || [];
  const heatmapData = matrix.flatMap((row, yIdx) =>
    row.map((v, xIdx) => [xIdx, yIdx, v])
  );
  const min = c.colorScale?.min ?? Math.min(...matrix.flatMap((r) => r));
  const max = c.colorScale?.max ?? Math.max(...matrix.flatMap((r) => r));
  return {
    grid: { left: 160, right: 80, top: 20, bottom: 20 },
    tooltip: {
      position: "top",
      formatter: (p: any) => {
        const [xIdx, yIdx, v] = p.data as [number, number, number];
        return `${yCats[yIdx]}<br/>${xCats[xIdx]}: <b>${v}</b>`;
      },
    },
    xAxis: { type: "category", data: xCats, splitArea: { show: true } },
    yAxis: { type: "category", data: yCats, splitArea: { show: true } },
    visualMap: {
      min,
      max,
      calculable: true,
      orient: "vertical",
      right: 10,
      top: "middle",
      inRange: {
        color: [
          c.colorScale?.lowColor || "#e0f7fa",
          c.colorScale?.highColor || "#d84315",
        ],
      },
      seriesIndex: [0],
    },
    series: [{ type: "heatmap", data: heatmapData }],
  };
}

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

/* -------- Aggregation helpers -------- */
function sumArrays(arrays: number[][]): number[] {
  if (!arrays.length) return [];
  const maxLen = Math.max(...arrays.map((a) => a.length));
  const result = new Array(maxLen).fill(0);
  arrays.forEach((a) => {
    for (let i = 0; i < maxLen; i++) result[i] += a[i] ?? 0;
  });
  return result;
}

interface AggregatedProductData {
  volume: number[];
  nps: number[];
  positive: number[];
  neutral: number[];
  negative: number[];
}

function aggregateSelectedProducts(
  selected: string[]
): AggregatedProductData | null {
  if (!selected.length || selected.includes("Все")) return null;
  const source = (data.productBreakdown?.products || []) as any[];
  const chosen = source.filter((p) => selected.includes(p.name));
  if (!chosen.length) return null;
  return {
    volume: sumArrays(chosen.map((p) => p.volume || [])),
    nps: sumArrays(chosen.map((p) => p.nps || [])),
    positive: sumArrays(chosen.map((p) => p.positive || [])),
    neutral: sumArrays(chosen.map((p) => p.neutral || [])),
    negative: sumArrays(chosen.map((p) => p.negative || [])),
  };
}

function aggregateHeatmapProducts(selected: string[], base: any): any {
  if (!selected.length || selected.includes("Все")) return base;
  if (!data.heatmapProductTopics) return base;
  const topics = (data as any).heatmapProductTopics;
  const monthCount = base?.xAxis?.length || 0;
  const categoryMap: Record<string, number[]> = {};
  selected.forEach((p) => {
    const ph = topics[p];
    if (!ph || !ph.yAxis || !ph.data) return;
    ph.yAxis.forEach((cat: string, idx: number) => {
      if (!categoryMap[cat]) categoryMap[cat] = new Array(monthCount).fill(0);
      const row = ph.data[idx] || [];
      for (let m = 0; m < monthCount; m++) categoryMap[cat][m] += row[m] ?? 0;
    });
  });
  const yAxis = Object.keys(categoryMap);
  const dataRows = yAxis.map((cat) => categoryMap[cat]);
  return { ...base, yAxis, data: dataRows };
}

/* ---------- Product Picker (Popup) ---------- */
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
    const withoutAll = selected.filter((s) => s !== "Все");
    if (withoutAll.includes(p)) {
      const next = withoutAll.filter((s) => s !== p);
      onChange(next.length ? next : ["Все"]);
    } else {
      onChange([...withoutAll, p]);
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

  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener("keydown", closeOnEsc);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("keydown", closeOnEsc);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [closeOnEsc, handleClickOutside]);

  const sorted = [...all].sort((a, b) =>
    a === "Все" ? -1 : b === "Все" ? 1 : a.localeCompare(b, "ru")
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 backdrop-blur-sm p-4">
      <div
        ref={ref}
        className="w-full max-w-md rounded-xl border bg-white dark:bg-[#1B1C1F] dark:border-[#2a2a2a] shadow-xl flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between px-5 h-12 border-b dark:border-[#2a2a2a]">
          <h3 className="font-semibold text-sm">Выбор продуктов</h3>
          <button
            onClick={onClose}
            className="text-xs px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-[#2a2a2a]"
          >
            ✕
          </button>
        </div>
        <div className="max-h-[50vh] overflow-auto px-5 py-3 flex flex-col gap-2">
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
                  все продукты
                </span>
              )}
            </label>
          ))}
        </div>
        <div className="flex items-center justify-between px-5 py-3 border-t dark:border-[#2a2a2a] gap-3">
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
export function TonalityDashboard() {
  if (!baseVolumeChart || !baseSentimentChart) {
    return <div className="p-6">Нет данных</div>;
  }

  const allProducts: string[] = data.filters?.products || ["Все"];
  const [selectedProducts, setSelectedProducts] = useState<string[]>(["Все"]);
  const [dateStart, setDateStart] = useState<string>(
    data.filters.dateRange.start
  );
  const [dateEnd, setDateEnd] = useState<string>(data.filters.dateRange.end);
  const [pickerOpen, setPickerOpen] = useState(false);

  const aggregated = useMemo(
    () => aggregateSelectedProducts(selectedProducts),
    [selectedProducts]
  );

  const volumeChart = useMemo(() => {
    if (!aggregated) return baseVolumeChart;
    if (!baseVolumeChart || !baseVolumeChart.series) return baseVolumeChart;
    return {
      ...baseVolumeChart,
      series: [
        { ...baseVolumeChart.series[0], data: aggregated.volume },
        { ...baseVolumeChart.series[1], data: aggregated.nps },
      ],
    };
  }, [aggregated]);

  const sentimentChart = useMemo(() => {
    if (!aggregated) return baseSentimentChart;
    if (!baseSentimentChart || !baseSentimentChart.series)
      return baseSentimentChart;
    return {
      ...baseSentimentChart,
      series: [
        { ...baseSentimentChart.series[0], data: aggregated.positive },
        { ...baseSentimentChart.series[1], data: aggregated.neutral },
        { ...baseSentimentChart.series[2], data: aggregated.negative },
      ],
    };
  }, [aggregated]);

  const heatmapChart = useMemo(
    () => aggregateHeatmapProducts(selectedProducts, baseHeatmapChart),
    [selectedProducts]
  );

  const filteredVolume = useMemo(
    () => filterByDate(volumeChart, dateStart, dateEnd),
    [volumeChart, dateStart, dateEnd]
  );
  const filteredSentiment = useMemo(
    () => filterByDate(sentimentChart, dateStart, dateEnd),
    [sentimentChart, dateStart, dateEnd]
  );
  const filteredHeatmap = useMemo(
    () => filterHeatmapByDate(heatmapChart, dateStart, dateEnd),
    [heatmapChart, dateStart, dateEnd]
  );

  const totalInRange = useMemo(() => {
    const vol = filteredVolume?.series?.[0]?.data || [];
    return vol.reduce((a: number, b: number) => a + (b || 0), 0);
  }, [filteredVolume]);

  const sentimentTotals = useMemo(() => {
    const series = filteredSentiment?.series || [];
    const sum = (regex: RegExp) => {
      const s = series.find((sr: any) => regex.test(sr.name));
      return (s?.data || []).reduce((a: number, b: number) => a + (b || 0), 0);
    };
    return {
      positive: sum(/Позитив/i),
      neutral: sum(/Нейтрал/i),
      negative: sum(/Негатив/i),
    };
  }, [filteredSentiment]);

  const isDark = useDarkMode();

  const optionVolume = useMemo(
    () => buildOptionVolumeNps(filteredVolume, isDark),
    [filteredVolume, isDark]
  );
  const optionSentiment = useMemo(
    () => buildOptionSentiment(filteredSentiment, isDark),
    [filteredSentiment, isDark]
  );
  const optionHeatmap = useMemo(
    () => buildOptionHeatmap(filteredHeatmap),
    [filteredHeatmap]
  );

  const optionSentimentPie = useMemo(() => {
    const textColor = isDark ? "#E5E7EB" : "#374151";
    const total =
      sentimentTotals.positive +
      sentimentTotals.neutral +
      sentimentTotals.negative;
    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        // NEW: позиционируем тултип справа от курсора (если хватает места, иначе слева)
        position: function (
          point: number[],
          params: any,
          dom: HTMLElement,
          rect: any,
          size: any
        ) {
          const [x, y] = point;
          const viewW = size.viewSize[0];
          const viewH = size.viewSize[1];
          const boxW = size.contentSize[0];
          const boxH = size.contentSize[1];
          const gap = 18;

          // Предпочтительно справа
          let left = x + gap;
          if (left + boxW > viewW) {
            // не влезает справа — переносим слева
            left = x - gap - boxW;
            if (left < 0) left = Math.max(0, viewW - boxW - 4);
          }

          // Вертикально центрируем относительно курсора
          let top = y - boxH / 2;
          if (top < 4) top = 4;
          if (top + boxH > viewH) top = viewH - boxH - 4;

          return [left, top];
        },
        confine: true,
        formatter: (p: any) =>
          `${p.marker} ${p.name}: <b>${p.value.toLocaleString("ru-RU")}</b> (${
            p.percent
          }%)`,
        extraCssText:
          "box-shadow:0 4px 12px rgba(0,0,0,0.18);padding:8px 10px;border-radius:6px;",
      },
      legend: {
        top: 0,
        left: 0,
        orient: "vertical",
        textStyle: { color: textColor, fontSize: 11 },
      },
      series: [
        {
          name: "Тональность",
          type: "pie",
          radius: ["50%", "70%"],
          center: ["50%", "58%"],
          avoidLabelOverlap: true,
          itemStyle: {
            borderRadius: 4,
            borderColor: "#fff",
            borderWidth: isDark ? 0 : 1,
          },
          color: ["#ff6b6b", "#9e9e9e", "#34c759"],
          label: {
            show: true,
            fontSize: 11,
            formatter: "{b}\n{d}%",
            color: textColor,
          },
          labelLine: { length: 10, length2: 8 },
          data: [
            { name: "Негативные", value: sentimentTotals.negative },
            { name: "Нейтральные", value: sentimentTotals.neutral },
            { name: "Позитивные", value: sentimentTotals.positive },
          ],
          emphasis: { scale: true, scaleSize: 6 },
        },
      ],
      graphic: [
        {
          type: "text",
          left: "center",
          top: "48%",
          style: {
            text: total.toLocaleString("ru-RU"),
            fontSize: 16,
            fontWeight: 600,
            fill: textColor,
            textAlign: "center",
          },
        },
        {
          type: "text",
          left: "center",
          top: "64%",
          style: {
            text: "Всего",
            fontSize: 11,
            fill: isDark ? "#9CA3AF" : "#6B7280",
            textAlign: "center",
          },
        },
      ],
    };
  }, [sentimentTotals, isDark]);

  const productsLabel = selectedProducts.includes("Все")
    ? "Все"
    : selectedProducts.length;

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER */}
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">
          Динамика тональности и объема обратной связи
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 w-full">
          Стратегический обзор: объем отзывов vs сглаженный NPS/CSI плюс
          разбивка тональности и heatmap проблемных тем для быстрого выявления
          трендов.
        </p>
      </header>

      {/* Фильтры */}
      <div className="flex flex-wrap items-end gap-6">
        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            Продукты
          </label>
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="flex items-center justify-between gap-2 font-medium text-sm px-4 py-2 min-w-[220px] border-t border-[#DDE1E6] bg-white dark:bg-[#1B1C1F] rounded cursor-pointer hover:bg-gray-50 dark:hover:bg-[#242529] transition-colors"
          >
            <span>
              {productsLabel === "Все"
                ? "Все продукты"
                : `Выбрано: ${productsLabel}`}
            </span>
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
            className="rounded font-medium text-sm px-4 py-2 min-w-[200px] border-t border-[#DDE1E6]"
            value={dateStart}
            min={data.filters.dateRange.start}
            max={data.filters.dateRange.end}
            onChange={(e) => setDateStart(e.target.value)}
          />
        </div>
        <div className="flex flex-col">
          <label className="px-4 py-0.5 font-medium text-sm text-gray-600 dark:text-[#666] mb-1">
            До
          </label>
          <input
            type="date"
            className="rounded font-medium text-sm px-4 py-2 min-w-[200px] border-t border-[#DDE1E6]"
            value={dateEnd}
            min={data.filters.dateRange.start}
            max={data.filters.dateRange.end}
            onChange={(e) => setDateEnd(e.target.value)}
          />
        </div>
      </div>

      {/* KPI блок */}
      <div className="flex flex-row flex-wrap items-start">
        <div className="flex flex-col flex-1">
          <span className="font-semibold mb-2">Распределение тональности</span>
          <div className="bg-white dark:bg-[#1B1C1F]">
            <ReactECharts
              key={`sentiment-pie-${isDark ? "dark" : "light"}`}
              option={optionSentimentPie}
              lazyUpdate
              style={{ height: "25vh", width: "100%" }}
            />
          </div>
        </div>

        <div className="flex flex-col flex-2 min-w-[320px]">
          <h2 className="font-semibold mb-2">
            Динамика тональности и объема обратной связи
          </h2>
          <ReactECharts
            key={`volume-${isDark ? "dark" : "light"}`}
            option={optionVolume}
            notMerge
            lazyUpdate
            style={{ height: "25vh", width: "100%" }}
          />
        </div>
      </div>

      {/* Остальные графики */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="font-semibold mb-2">Тональность отзывов</h2>
          <ReactECharts
            key={`sentiment-${isDark ? "dark" : "light"}`}
            option={optionSentiment}
            notMerge
            lazyUpdate
            style={{ height: "23vh", width: "100%" }}
          />
        </div>
        <div>
          <h2 className="font-semibold mb-2">Карта тепла проблемных тем</h2>
          <ReactECharts
            key={`heat-${isDark ? "dark" : "light"}`}
            option={optionHeatmap}
            notMerge
            lazyUpdate
            style={{ height: "23vh", width: "100%" }}
          />
        </div>
      </div>

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
