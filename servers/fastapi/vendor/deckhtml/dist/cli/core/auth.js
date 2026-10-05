"use strict";
/**
 * Browser login flow with local callback server
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.DEFAULT_PORT = void 0;
exports.buildLoginUrl = buildLoginUrl;
exports.buildCheckoutUrl = buildCheckoutUrl;
exports.runLoginFlow = runLoginFlow;
exports.runCheckoutFlow = runCheckoutFlow;
const http_1 = __importDefault(require("http"));
const LOGIN_TIMEOUT = 300000;
const DEFAULT_PORT = 3737;
exports.DEFAULT_PORT = DEFAULT_PORT;
function isChinesePreferredLanguage(acceptLanguageHeader) {
    const raw = Array.isArray(acceptLanguageHeader)
        ? acceptLanguageHeader.join(',')
        : (acceptLanguageHeader ?? '');
    return raw.toLowerCase().includes('zh');
}
function isChineseCliLocale() {
    const locale = process.env.LC_ALL || process.env.LC_MESSAGES || process.env.LANG || '';
    return locale.toLowerCase().includes('zh');
}
async function openBrowser(url) {
    const { default: open } = await import('open');
    await open(url);
}
function startCallbackServer(port) {
    return new Promise((resolve, reject) => {
        let settled = false;
        let timeoutHandle;
        const settleResolve = (value) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(timeoutHandle);
            resolve(value);
        };
        const settleReject = (error) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(timeoutHandle);
            reject(error);
        };
        const server = http_1.default.createServer((req, res) => {
            const url = new URL(req.url || '', `http://localhost:${port}`);
            const token = url.searchParams.get('token');
            const spaceId = url.searchParams.get('spaceId') ||
                url.searchParams.get('space_id') ||
                undefined;
            const isZh = isChinesePreferredLanguage(req.headers['accept-language']);
            const pageTitle = isZh ? '登录成功' : 'Login Successful';
            const pageHeading = isZh ? '登录成功！' : 'Login Successful!';
            const pageDescription = isZh
                ? '你可以关闭此窗口并返回终端。'
                : 'You can close this window and return to your terminal.';
            if (token) {
                res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
                res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${pageTitle}</title></head><body><h1>${pageHeading}</h1><p>${pageDescription}</p></body></html>`);
                settleResolve({ token, spaceId: spaceId || undefined, server });
            }
            else {
                res.writeHead(400, { 'Content-Type': 'text/plain' });
                res.end('Missing token parameter');
            }
        });
        server.on('error', (err) => {
            if (err.code === 'EADDRINUSE') {
                settleReject(new Error(`Port ${port} is already in use. Please close other applications and try again.`));
            }
            else {
                settleReject(err);
            }
        });
        server.listen(port);
        timeoutHandle = setTimeout(() => {
            server.close();
            settleReject(new Error('Login timeout. Please try again.'));
        }, LOGIN_TIMEOUT);
    });
}
function startRedirectServer(port) {
    return new Promise((resolve, reject) => {
        let settled = false;
        let timeoutHandle;
        const settleResolve = (value) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(timeoutHandle);
            resolve(value);
        };
        const settleReject = (error) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(timeoutHandle);
            reject(error);
        };
        const server = http_1.default.createServer((req, res) => {
            const isZh = isChinesePreferredLanguage(req.headers['accept-language']);
            const pageTitle = isZh ? '完成' : 'Done';
            const pageHeading = isZh ? '完成' : 'Done';
            const pageDescription = isZh
                ? '你可以关闭此窗口并返回终端。'
                : 'You can close this window and return to your terminal.';
            res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${pageTitle}</title></head><body><h1>${pageHeading}</h1><p>${pageDescription}</p></body></html>`);
            settleResolve({ server });
        });
        server.on('error', (err) => {
            if (err.code === 'EADDRINUSE') {
                settleReject(new Error(`Port ${port} is already in use. Please close other applications and try again.`));
            }
            else {
                settleReject(err);
            }
        });
        server.listen(port);
        timeoutHandle = setTimeout(() => {
            server.close();
            settleReject(new Error('Operation timeout. Please try again.'));
        }, LOGIN_TIMEOUT);
    });
}
function normalizeLoginBase(apiBase) {
    const u = new URL(apiBase);
    u.pathname = u.pathname.replace(/\/v1\/?$/, '/');
    return `${u.origin}${u.pathname}`.replace(/\/$/, '');
}
function buildLoginUrl(apiBase, callbackUrl) {
    const loginBase = normalizeLoginBase(apiBase);
    return `${loginBase}/cli/auth?redirect_url=${encodeURIComponent(callbackUrl)}`;
}
function buildCheckoutUrl(options) {
    const base = normalizeLoginBase(options.apiBase);
    const u = new URL(`${base}/cli/checkout`);
    u.searchParams.set('redirect_url', options.redirectUrl);
    u.searchParams.set('token', options.token);
    if (options.spaceId) {
        u.searchParams.set('spaceId', options.spaceId);
    }
    return u.toString();
}
async function runLoginFlow(options) {
    const isZh = isChineseCliLocale();
    const callbackUrl = `http://localhost:${options.port}`;
    const loginUrl = buildLoginUrl(options.apiBase, callbackUrl);
    if (!options.jsonOutput) {
        if (options.reason === 'guest-limit') {
            console.error(isZh
                ? '\n游客模式的云端使用次数已达上限（或云端已要求登录）。登录或配置 API Key 后即可继续。\n'
                : '\nGuest cloud usage limit reached (or sign-in is now required). Log in or set an API key to continue.\n');
            console.error(isZh
                ? '提示：也可以直接运行 `deckhtml config set api-key <key>` 配置 API Key，无需浏览器登录。\n'
                : 'Tip: you can also run `deckhtml config set api-key <key>` to set an API key without browser login.\n');
        }
        else if (options.reason === 'unauthorized') {
            console.error(isZh
                ? '\n认证已失效，需要重新登录。\n'
                : '\nAuthentication expired. Please log in again.\n');
        }
        else {
            console.error(isZh ? '\n🔐 DeckHTML 登录\n' : '\n🔐 DeckHTML Login\n');
        }
        console.error(`Opening browser to: ${loginUrl}`);
        console.error(`Waiting for authentication on port ${options.port}...\n`);
    }
    const serverPromise = startCallbackServer(options.port);
    try {
        await openBrowser(loginUrl);
    }
    catch {
        if (!options.jsonOutput) {
            console.error(isZh
                ? '\n无法自动打开浏览器，请手动打开此链接：\n'
                : '\nUnable to open browser automatically. Please open this link:\n');
            console.error(`${loginUrl}\n`);
        }
    }
    const { token, spaceId, server } = await serverPromise;
    server.close();
    if (!options.jsonOutput) {
        console.error('Login successful!\n');
    }
    return { token, spaceId };
}
async function runCheckoutFlow(options) {
    const isZh = isChineseCliLocale();
    const redirectUrl = `http://localhost:${options.port}`;
    const checkoutUrl = buildCheckoutUrl({
        apiBase: options.apiBase,
        redirectUrl,
        token: options.token,
        spaceId: options.spaceId,
    });
    if (!options.jsonOutput) {
        console.error(isZh
            ? '\n余额不足，需要购买后继续。\n'
            : '\nInsufficient balance. Please complete payment to continue.\n');
        console.error(`Opening browser to: ${checkoutUrl}`);
        console.error(`Waiting for checkout completion on port ${options.port}...\n`);
    }
    const serverPromise = startRedirectServer(options.port);
    try {
        await openBrowser(checkoutUrl);
    }
    catch {
        if (!options.jsonOutput) {
            console.error(isZh
                ? '\n无法自动打开浏览器，请手动打开此链接：\n'
                : '\nUnable to open browser automatically. Please open this link:\n');
            console.error(`${checkoutUrl}\n`);
        }
    }
    const { server } = await serverPromise;
    server.close();
    if (!options.jsonOutput) {
        console.error('Checkout completed!\n');
    }
}
