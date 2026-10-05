export interface IsChineseFontOptions {
    /**
     * 是否先提取字体核心名（忽略 regular/bold/italic/常规/粗体 等后缀）。
     * @default true
     */
    stripStyleSuffix?: boolean;
}
/** 去除字体名中常见样式后缀，仅保留核心家族名 */
export declare function extractCoreFontName(s: string): string;
/** 拆字体栈为单个家族名字符串 */
export declare function splitFontStack(fontStack: string): string[];
/**
 * 判断给定字体名称（可为单个家族名或一整段 font-family 栈）是否属于中文字体。
 * 执行路径：提取核心名 -> Set.has（O(1)）
 */
export declare function isChineseFont(fontNameOrStack: string, options?: IsChineseFontOptions): boolean;
/** 返回栈中命中的核心名称，未命中返回 null。 */
export declare function matchChineseFontAlias(fontNameOrStack: string): string | null;
