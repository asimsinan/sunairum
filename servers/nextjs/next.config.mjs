/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Default rewrite proxyTimeout is 30s; image gen (OpenRouter) often needs minutes.
  experimental: {
    proxyTimeout: 1000 * 60 * 5,
  },
  // Next 14.2 can drop page CSS-module chunks on client navigations while layout
  // CSS still applies (sidebar styled, home composer unstyled). Disable the
  // experimental CSS chunker in dev — see vercel/next.js#64404.
  webpack(config, { dev }) {
    if (dev) {
      config.plugins = config.plugins.filter(
        (plugin) => plugin?.constructor?.name !== 'CssChunkingPlugin',
      )
    }
    return config
  },
  async rewrites() {
    // Local/dev: first-party /api and /ws so session cookies stay SameSite=Lax.
    // Production cloud: Caddy already terminates TLS and proxies these paths;
    // rewrites to localhost:8000 are unused when the browser hits Caddy.
    const api = (process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000').replace(/\/+$/, '')
    return [
      { source: '/api/:path*', destination: `${api}/api/:path*` },
      { source: '/ws/:path*', destination: `${api}/ws/:path*` },
      { source: '/health', destination: `${api}/health` },
      { source: '/storage/:path*', destination: `${api}/storage/:path*` },
    ]
  },
}

export default nextConfig
