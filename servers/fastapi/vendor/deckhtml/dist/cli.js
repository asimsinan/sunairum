#!/usr/bin/env node
"use strict";
/**
 * DeckHTML CLI entry point
 */
Object.defineProperty(exports, "__esModule", { value: true });
const fs_1 = require("fs");
const path_1 = require("path");
const commander_1 = require("commander");
const context_1 = require("./cli/context");
const auth_1 = require("./cli/commands/auth");
const config_1 = require("./cli/commands/config");
const convert_1 = require("./cli/commands/convert");
const errors_1 = require("./cli/utils/errors");
const update_notifier_1 = require("./utils/update-notifier");
const packageJson = JSON.parse((0, fs_1.readFileSync)((0, path_1.join)(__dirname, '../package.json'), 'utf-8'));
const CLI_NAME = packageJson.name ?? '@deckflow/deckhtml';
const CLI_VERSION = packageJson.version ?? '0.0.0';
async function main() {
    const ctx = new context_1.Context();
    await ctx.init();
    // 静默检查并提示升级到最新版（失败不影响主流程）
    await (0, update_notifier_1.notifyUpdate)({ name: CLI_NAME, version: CLI_VERSION });
    const program = new commander_1.Command();
    program
        .name('deckhtml')
        .description('Convert HTML to PPTX or PNG')
        .version(CLI_VERSION, '-V, --version', 'Show version')
        .helpOption('-h, --help', 'Show help')
        .option('--json', 'Machine-readable JSON on stdout')
        .option('-v, --verbose', 'Detailed logs to stderr')
        .option('--quiet', 'Only errors and final result')
        .hook('preAction', (thisCommand) => {
        const opts = thisCommand.optsWithGlobals();
        if (opts.verbose && opts.quiet) {
            ctx.fatal('usage_error', '--quiet conflicts with --verbose');
        }
        ctx.jsonOutput = Boolean(opts.json);
        ctx.verbose = Boolean(opts.verbose);
        ctx.quiet = Boolean(opts.quiet);
    });
    (0, config_1.registerConfigCommands)(program, ctx);
    (0, auth_1.registerAuthCommands)(program, ctx);
    (0, convert_1.registerConvertCommand)(program, ctx);
    try {
        await program.parseAsync(process.argv);
    }
    catch (error) {
        if (error instanceof commander_1.CommanderError) {
            if (error.code === 'commander.help' ||
                error.code === 'commander.helpDisplayed') {
                process.exit(error.exitCode ?? 0);
            }
            if (error.code === 'commander.version') {
                process.exit(0);
            }
        }
        (0, errors_1.outputError)(error instanceof Error ? error : new Error(String(error)), ctx.jsonOutput, 'ERROR', { apiBase: ctx.config.apiBase });
        process.exit(errors_1.ExitCode.ERROR);
    }
    const args = process.argv.slice(2);
    const hasSubcommand = args[0] === 'auth' || args[0] === 'config';
    if (args.length === 0 || (!hasSubcommand && args.every((a) => a.startsWith('-')))) {
        program.help();
    }
}
main().catch((error) => {
    console.error('Fatal error:', error);
    process.exit(errors_1.ExitCode.ERROR);
});
