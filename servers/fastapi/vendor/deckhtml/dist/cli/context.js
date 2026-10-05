"use strict";
/**
 * CLI context: config, SDK client, auth, output helpers
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.Context = void 0;
const config_1 = require("./core/config");
const auth_1 = require("./core/auth");
const api_error_1 = require("./utils/api-error");
const errors_1 = require("./utils/errors");
class Context {
    constructor() {
        this.jsonOutput = false;
        this.verbose = false;
        this.quiet = false;
        this.config = new config_1.Config();
    }
    async init() {
        await this.config.load();
    }
    resolveApiKey() {
        return process.env.DECKHTML_API_KEY || this.config.get('apiKey');
    }
    hasCredentials() {
        return Boolean(this.resolveApiKey() || this.config.get('token'));
    }
    async getDeck() {
        const apiKey = this.resolveApiKey();
        const token = this.config.get('token');
        const hadCredentials = Boolean(apiKey || token);
        if (!this.deck) {
            await (0, api_error_1.installApiErrorCapture)({
                logRequests: (0, api_error_1.shouldLogHttpRequests)(this.verbose),
            });
            const { createDeck } = await import('@deckops/sdk');
            this.deck = createDeck({
                root: this.config.apiBase,
                apiKey,
                token,
                spaceId: this.config.get('spaceId'),
                onUnauthorized: async () => {
                    // Guests (UUID-only) reach here when the server rejects them with
                    // 401 (rate limit or guest access disabled); authenticated users
                    // reach here when their token expired.
                    const nextToken = await this.ensureLoggedIn(auth_1.DEFAULT_PORT, hadCredentials ? 'unauthorized' : 'guest-limit');
                    return { token: nextToken, spaceId: this.config.get('spaceId') };
                },
                onPaymentRequired: async () => {
                    await this.ensureCheckout();
                },
            });
        }
        return this.deck;
    }
    resetDeck() {
        this.deck = undefined;
    }
    async ensureLoggedIn(port = auth_1.DEFAULT_PORT, reason = 'unauthorized') {
        if (this.loginPromise) {
            return this.loginPromise;
        }
        this.loginPromise = (async () => {
            const { token, spaceId } = await (0, auth_1.runLoginFlow)({
                apiBase: this.config.apiBase,
                port,
                jsonOutput: this.jsonOutput,
                reason,
            });
            await this.config.setToken(token);
            if (spaceId) {
                await this.config.setSpaceId(spaceId);
            }
            this.resetDeck();
            if (this.deck) {
                this.deck.setToken(token);
                this.deck.setSpaceId(this.config.get('spaceId'));
            }
            return token;
        })();
        try {
            return await this.loginPromise;
        }
        finally {
            this.loginPromise = undefined;
        }
    }
    async ensureCheckout(port = auth_1.DEFAULT_PORT) {
        if (this.checkoutPromise) {
            return this.checkoutPromise;
        }
        this.checkoutPromise = (async () => {
            const token = this.config.get('token');
            if (!token) {
                await this.ensureLoggedIn(port, 'unauthorized');
            }
            await (0, auth_1.runCheckoutFlow)({
                apiBase: this.config.apiBase,
                port,
                jsonOutput: this.jsonOutput,
                token: this.config.get('token'),
                spaceId: this.config.get('spaceId'),
            });
        })();
        try {
            await this.checkoutPromise;
        }
        finally {
            this.checkoutPromise = undefined;
        }
    }
    output(data, humanFormat) {
        if (this.jsonOutput) {
            console.log(JSON.stringify(data, null, 2));
        }
        else if (humanFormat) {
            console.log(humanFormat(data));
        }
        else {
            console.log(data);
        }
    }
    error(input, code = 'ERROR', exitCode = errors_1.ExitCode.ERROR) {
        const err = input instanceof Error ? input : new Error(String(input ?? 'Unknown error'));
        (0, errors_1.outputError)(err, this.jsonOutput, code, { apiBase: this.config.apiBase });
        process.exit(exitCode);
    }
    fatal(code, message) {
        this.error(new Error(message), code, errors_1.ExitCode.USAGE_ERROR);
    }
}
exports.Context = Context;
