/**
 * Browser login flow with local callback server
 */
declare const DEFAULT_PORT = 3737;
export declare function buildLoginUrl(apiBase: string, callbackUrl: string): string;
export declare function buildCheckoutUrl(options: {
    apiBase: string;
    redirectUrl: string;
    token: string;
    spaceId?: string;
}): string;
export declare function runLoginFlow(options: {
    apiBase: string;
    port: number;
    jsonOutput: boolean;
    reason?: 'explicit' | 'unauthorized' | 'guest-limit';
}): Promise<{
    token: string;
    spaceId?: string;
}>;
export declare function runCheckoutFlow(options: {
    apiBase: string;
    port: number;
    jsonOutput: boolean;
    token: string;
    spaceId?: string;
}): Promise<void>;
export { DEFAULT_PORT };
