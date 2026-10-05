"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerAuthCommands = registerAuthCommands;
const auth_1 = require("../core/auth");
function registerAuthCommands(program, ctx) {
    const auth = program.command('auth').description('Authentication commands');
    auth
        .command('login')
        .description('Login via browser and save credentials')
        .option('--port <port>', 'Local callback port', String(auth_1.DEFAULT_PORT))
        .action(async (options) => {
        try {
            const port = parseInt(options.port, 10);
            if (!Number.isFinite(port) || port <= 0 || port > 65535) {
                throw new Error(`Invalid --port: ${options.port}`);
            }
            await ctx.ensureLoggedIn(port, 'explicit');
            ctx.output({ success: true, message: 'Login successful' }, () => 'Login successful');
        }
        catch (error) {
            ctx.error(error);
        }
    });
    auth
        .command('status')
        .description('Show authentication status')
        .action(() => {
        try {
            const apiKey = ctx.resolveApiKey();
            const token = ctx.config.get('token');
            const spaceId = ctx.config.get('spaceId');
            ctx.output({
                apiKey: Boolean(apiKey),
                token: Boolean(token),
                spaceId: spaceId ?? null,
                configFile: ctx.config.configFilePath,
            }, (data) => {
                const record = data;
                return [
                    `API key: ${record.apiKey ? 'set' : 'not set'}`,
                    `Token: ${record.token ? 'set' : 'not set'}`,
                    `Space ID: ${record.spaceId ?? '(not set)'}`,
                    `Config: ${record.configFile}`,
                ].join('\n');
            });
        }
        catch (error) {
            ctx.error(error);
        }
    });
}
