#!/usr/bin/env bash
#
# Opens TCP 80/443 on the host firewall.
#
# Oracle Cloud Ubuntu images keep iptables rules that accept SSH and reject
# everything else. Opening ports in the VCN security list alone is not enough;
# these host rules must allow HTTP/HTTPS too, or the Droplet-equivalent looks
# unreachable ("No route to host").
#
#   sudo ./deploy/oracle/open-firewall.sh
#
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'Run as root: sudo %s\n' "$0" >&2
  exit 1
fi

ensure_accept() {
  local port="$1"
  if iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    printf '==> iptables already allows tcp/%s\n' "$port"
    return
  fi
  # Insert near the top (before the default REJECT), matching Oracle's docs.
  iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
  printf '==> Allowed tcp/%s in iptables\n' "$port"
}

ensure_accept 80
ensure_accept 443

if command -v netfilter-persistent >/dev/null 2>&1; then
  netfilter-persistent save
elif [[ -d /etc/iptables ]]; then
  iptables-save >/etc/iptables/rules.v4
  printf '==> Saved rules to /etc/iptables/rules.v4\n'
else
  printf '==> Warning: could not persist iptables rules; re-run after reboot if needed\n' >&2
fi

printf '\nAlso add Ingress rules in the OCI console (VCN → Security List):\n'
printf '  TCP 80  from 0.0.0.0/0\n'
printf '  TCP 443 from 0.0.0.0/0\n'
printf '  TCP 22  from your IP (or 0.0.0.0/0 for short beta)\n'
