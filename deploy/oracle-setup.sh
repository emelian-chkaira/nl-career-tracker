#!/bin/sh
# One-time server setup for an Ubuntu VM on Oracle Cloud (also fine on any Ubuntu/Debian VPS).  Run as the default user:  sh deploy/oracle-setup.sh
set -e
echo "== Docker"
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sudo sh; fi
sudo usermod -aG docker "$USER"
echo "== Firewall: Oracle's Ubuntu images ship with iptables rules that only allow SSH"
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo sh -c 'command -v netfilter-persistent >/dev/null || (apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent)'
sudo netfilter-persistent save
echo "== Swap (4 GB) so the image build and the embedding model have headroom"
if [ ! -f /swapfile ]; then sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null; fi
echo "Done. Log out and back in (docker group), then follow docs/DEPLOY_ORACLE.md step 5."
