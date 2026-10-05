/**
 * CLI context: config, SDK client, auth, output helpers
 */
import type { DeckClient } from './types/sdk';
import { Config } from './core/config';
export declare class Context {
    config: Config;
    jsonOutput: boolean;
    verbose: boolean;
    quiet: boolean;
    private deck?;
    private loginPromise?;
    private checkoutPromise?;
    constructor();
    init(): Promise<void>;
    resolveApiKey(): string | undefined;
    hasCredentials(): boolean;
    getDeck(): Promise<DeckClient>;
    resetDeck(): void;
    ensureLoggedIn(port?: number, reason?: 'explicit' | 'unauthorized' | 'guest-limit'): Promise<string>;
    ensureCheckout(port?: number): Promise<void>;
    output(data: unknown, humanFormat?: (data: unknown) => string): void;
    error(input: unknown, code?: string, exitCode?: number): never;
    fatal(code: string, message: string): never;
}
