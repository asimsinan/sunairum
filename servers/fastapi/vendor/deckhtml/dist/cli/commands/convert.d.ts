import { Command } from 'commander';
import { Context } from '../context';
export interface ConvertOptions {
    output?: string;
    mode: string;
    width?: string;
    platform?: string;
    embedFonts?: boolean;
    report?: boolean;
    executablePath?: string;
    exclude?: string;
    identityAttribute?: string;
    force?: boolean;
    /** commander --no-animations sets this to false (default true). */
    animations?: boolean;
    /**
     * Slide-to-slide transition effect name(s) (`fade`, `push`, or `fade,push,wipe`)
     * or `random`. From `--slide-transition <name[,name…]>`. Default when unset: random.
     */
    slideTransition?: string;
    /**
     * commander `--no-slide-transitions` sets this to false (default true).
     * When false, disables slide-to-slide transitions.
     */
    slideTransitions?: boolean;
    /**
     * How to handle `<iframe>` elements: `inspect` (default), `screenshot`, or `skip`.
     * From `--iframes <mode>`. Local mode only.
     */
    iframes?: string;
    /** Timeout (ms) for loading iframe documents in a new page. From `--iframe-load-timeout-ms`. */
    iframeLoadTimeoutMs?: string;
}
export declare function registerConvertCommand(program: Command, ctx: Context): void;
