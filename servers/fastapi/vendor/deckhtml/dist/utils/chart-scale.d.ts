/**
 * Chart payload helpers — mixed Cost/CV scales and dual-axis prep for pptxgen.
 */
export type ChartSeriesIn = {
    name?: string;
    values?: Array<number | string>;
};
export type ChartPayloadIn = {
    type?: string;
    categories?: Array<string | number>;
    series?: ChartSeriesIn[];
    /** Hex colours (no '#') the HTML preview painted, in series/category order. */
    colors?: string[];
};
export type ChartSeriesOut = {
    name: string;
    /**
     * `null` marks a slot this series does not occupy. A zero would draw a
     * zero-height bar *and* its data label, printing a stray "0" beside the
     * neighbour's real value; a blank cell draws neither.
     */
    values: Array<number | null>;
    /** Plot on secondary value axis (mixed-scale charts). */
    secondary?: boolean;
};
export type PreparedChart = {
    chartType: 'bar' | 'col' | 'line' | 'pie';
    categories: string[];
    series: ChartSeriesOut[];
    dualAxis: boolean;
    /** True when values were restructured from mixed-scale categories. */
    mixedScale: boolean;
    /** Per-series hex colours, aligned to `series`, when the deck supplied them. */
    colors?: string[];
};
export declare function isMixedScale(values: number[]): boolean;
/**
 * Prepare chart data for PPTX.
 *
 * Cost (~2e5) and CV (~1.2) as one series share a Y-axis → CV bar vanishes in
 * PowerPoint (HTML preview fakes visibility with an 8% floor). Restructure to
 * dual-axis series so both metrics read.
 */
export declare function prepareChartPayload(payload: ChartPayloadIn): PreparedChart;
