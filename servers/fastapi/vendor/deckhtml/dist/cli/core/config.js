"use strict";
/**
 * Persistent CLI configuration at ~/.deckflow/credentials
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.Config = void 0;
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
const os_1 = __importDefault(require("os"));
const DEFAULT_CONFIG_DIR = path_1.default.join(os_1.default.homedir(), '.deckflow');
const CONFIG_FILE = 'credentials';
const DEFAULT_API_BASE = 'https://app.deckflow.com/v1';
const DEFAULT_RETENTION_HOURS = 3;
const CONFIG_KEYS = [
    'apiKey',
    'token',
    'spaceId',
    'apiBase',
    'webhook',
    'retentionHours',
];
function sanitizeConfig(raw) {
    const data = {};
    for (const key of CONFIG_KEYS) {
        const value = raw[key];
        if (value !== undefined) {
            data[key] = value;
        }
    }
    return data;
}
function hasLegacyKeys(raw) {
    return Object.keys(raw).some((key) => !CONFIG_KEYS.includes(key));
}
class Config {
    constructor(configDir) {
        this.data = {};
        this.configDir =
            configDir || process.env.DECKHTML_CONFIG_DIR || DEFAULT_CONFIG_DIR;
        this.configPath = path_1.default.join(this.configDir, CONFIG_FILE);
    }
    async load() {
        try {
            const raw = await promises_1.default.readFile(this.configPath, 'utf-8');
            const parsed = JSON.parse(raw);
            this.data = sanitizeConfig(parsed);
            if (hasLegacyKeys(parsed)) {
                await this.save();
            }
        }
        catch {
            this.data = {};
        }
    }
    async save() {
        await promises_1.default.mkdir(this.configDir, { recursive: true });
        await promises_1.default.writeFile(this.configPath, `${JSON.stringify(this.data, null, 2)}\n`, 'utf-8');
    }
    get(key, defaultValue) {
        return this.data[key] ?? defaultValue;
    }
    async set(key, value) {
        this.data[key] = value;
        await this.save();
    }
    all() {
        return sanitizeConfig(this.data);
    }
    get apiBase() {
        return this.data.apiBase || DEFAULT_API_BASE;
    }
    get retentionHours() {
        return this.data.retentionHours ?? DEFAULT_RETENTION_HOURS;
    }
    async setApiKey(value) {
        this.data.apiKey = value;
        await this.save();
    }
    async setToken(value) {
        this.data.token = value;
        await this.save();
    }
    async setSpaceId(value) {
        this.data.spaceId = value;
        await this.save();
    }
    isConfigured() {
        return Boolean(this.data.apiKey || this.data.token);
    }
    get configFilePath() {
        return this.configPath;
    }
}
exports.Config = Config;
