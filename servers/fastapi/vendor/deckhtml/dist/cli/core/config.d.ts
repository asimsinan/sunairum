/**
 * Persistent CLI configuration at ~/.deckflow/credentials
 */
export interface DeckhtmlConfigData {
    apiKey?: string;
    token?: string;
    spaceId?: string;
    apiBase?: string;
    webhook?: string;
    retentionHours?: number;
}
export declare class Config {
    private readonly configDir;
    private readonly configPath;
    private data;
    constructor(configDir?: string);
    load(): Promise<void>;
    save(): Promise<void>;
    get<K extends keyof DeckhtmlConfigData>(key: K, defaultValue?: DeckhtmlConfigData[K]): DeckhtmlConfigData[K] | undefined;
    set<K extends keyof DeckhtmlConfigData>(key: K, value: DeckhtmlConfigData[K]): Promise<void>;
    all(): DeckhtmlConfigData;
    get apiBase(): string;
    get retentionHours(): number;
    setApiKey(value: string): Promise<void>;
    setToken(value: string): Promise<void>;
    setSpaceId(value: string): Promise<void>;
    isConfigured(): boolean;
    get configFilePath(): string;
}
