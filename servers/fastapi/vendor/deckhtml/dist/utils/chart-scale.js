"use strict";
/**
 * Chart payload helpers — mixed Cost/CV scales and dual-axis prep for pptxgen.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.isMixedScale = isMixedScale;
exports.prepareChartPayload = prepareChartPayload;
const MIXED_SCALE_RATIO = 20;
function toNums(values) {
    return (values || []).map((v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
    });
}
function isMixedScale(values) {
    const pos = values.map((v) => Math.abs(v)).filter((v) => v > 0);
    if (pos.length < 2)
        return false;
    return Math.max(...pos) / Math.min(...pos) >= MIXED_SCALE_RATIO;
}
function resolveChartType(raw) {
    const t = String(raw ?? '')
        .trim()
        .toLowerCase()
        .replace(/[\s_-]+/g, '');
    if (t === 'bar' || t === 'barchart' || t === 'horizontalbar')
        return 'bar';
    if (t === 'line' || t === 'linechart')
        return 'line';
    if (t === 'pie' || t === 'piechart')
        return 'pie';
    return 'col';
}
/**
 * Prepare chart data for PPTX.
 *
 * Cost (~2e5) and CV (~1.2) as one series share a Y-axis → CV bar vanishes in
 * PowerPoint (HTML preview fakes visibility with an 8% floor). Restructure to
 * dual-axis series so both metrics read.
 */
function prepareChartPayload(payload) {
    const chartType = resolveChartType(payload.type);
    const palette = (payload.colors || [])
        .map((c) => String(c || '').replace(/^#/, '').toUpperCase())
        .filter((c) => /^[0-9A-F]{6}$/.test(c));
    const categories = (payload.categories ?? []).map((c) => String(c));
    const rawSeries = (payload.series ?? []).map((s) => ({
        name: String(s?.name ?? 'Series'),
        values: toNums(s?.values),
    }));
    if (chartType === 'pie' || chartType === 'line') {
        return {
            chartType,
            categories,
            series: rawSeries,
            dualAxis: false,
            mixedScale: false,
            colors: palette,
        };
    }
    // Single series, multi-category (Cost | CV): promote each category to its own series.
    if (rawSeries.length === 1 && categories.length >= 2) {
        const vals = rawSeries[0].values;
        if (isMixedScale(vals.slice(0, categories.length))) {
            const abs = vals.map((v) => Math.abs(v));
            const globalMax = Math.max(...abs, 0);
            // Each promoted series keeps its own category slot and is zero in the
            // others. Collapsing them all onto a single unnamed category put both
            // bars at the same x, so the taller one covered the other: the exported
            // card showed one bar, a data label reading "0", and a phantom "Series1"
            // where the category name should have been. A zero-height bar in a
            // neighbour's slot paints nothing, so the only visible mark per slot is
            // the metric that belongs there.
            const series = categories.map((cat, i) => {
                const v = vals[i] ?? 0;
                const secondary = globalMax > 0 && Math.abs(v) > 0 && globalMax / Math.abs(v) >= MIXED_SCALE_RATIO;
                const slotted = categories.map((_c, j) => j === i ? v : null);
                return { name: cat, values: slotted, secondary };
            });
            // Ensure at least one primary series (largest magnitude).
            if (series.every((s) => s.secondary)) {
                let best = 0;
                const own = (i) => Math.abs(series[i].values[i] ?? 0);
                for (let i = 1; i < series.length; i++) {
                    if (own(i) > own(best))
                        best = i;
                }
                series[best].secondary = false;
            }
            return {
                chartType,
                categories,
                series,
                dualAxis: series.some((s) => s.secondary),
                mixedScale: true,
                colors: palette,
            };
        }
    }
    // Multi-series with incompatible scales (e.g. Cost series vs CV series).
    if (rawSeries.length >= 2) {
        const maxima = rawSeries.map((s) => Math.max(0, ...s.values.map((v) => Math.abs(v))));
        const globalMax = Math.max(...maxima, 0);
        if (globalMax > 0 && maxima.some((m) => m > 0 && globalMax / m >= MIXED_SCALE_RATIO)) {
            const series = rawSeries.map((s, i) => ({
                name: s.name,
                values: s.values,
                secondary: maxima[i] > 0 && globalMax / maxima[i] >= MIXED_SCALE_RATIO,
            }));
            if (series.every((s) => s.secondary)) {
                let best = 0;
                for (let i = 1; i < maxima.length; i++) {
                    if (maxima[i] > maxima[best])
                        best = i;
                }
                series[best].secondary = false;
            }
            return {
                chartType,
                categories,
                series,
                dualAxis: series.some((s) => s.secondary),
                mixedScale: true,
                colors: palette,
            };
        }
    }
    return {
        chartType,
        categories,
        series: rawSeries,
        dualAxis: false,
        mixedScale: false,
        colors: palette,
    };
}
