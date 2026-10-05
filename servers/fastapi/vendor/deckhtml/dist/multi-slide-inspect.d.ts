import { HTMLLoader } from './loader';
import { InspectElementsOptions, SlideContainerDiscovery } from './inspector';
import { ElementInfo } from './types';
export interface InspectSlidesParallelParams {
    inputPath: string;
    viewport: {
        width: number;
        height: number;
    };
    allowLocalResources?: boolean;
    resourcePolicy?: import('./utils/resource-policy').ResourcePolicy;
    diagnostics?: import('./utils/resource-policy').ResourceDiagnostic[];
    slideSelector?: string;
    autoDetectSlides: boolean;
    discovery: SlideContainerDiscovery;
    inspectOptions: InspectElementsOptions;
    concurrency: number;
}
/**
 * Inspect each slide in its own Playwright page, with a bounded page pool.
 */
export declare function inspectSlidesParallel(loader: HTMLLoader, params: InspectSlidesParallelParams): Promise<Map<number, ElementInfo[]>>;
