export interface ApiErrorDetails {
    message: string;
    requestUrl?: string;
    method?: string;
    statusCode?: number;
    requestId?: string;
    responseData?: unknown;
}
export declare function buildRequestUrl(apiBase: string | undefined, details: Pick<ApiErrorDetails, 'requestUrl' | 'message'>): string | undefined;
export declare function toApiErrorDetails(error: unknown, apiBase?: string): ApiErrorDetails | undefined;
export declare function formatApiErrorLines(details: ApiErrorDetails, apiBase?: string): string[];
export declare function installApiErrorCapture(options?: {
    logRequests?: boolean;
}): Promise<void>;
export declare function shouldLogHttpRequests(verbose: boolean): boolean;
