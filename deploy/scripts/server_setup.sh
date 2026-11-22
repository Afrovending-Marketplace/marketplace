#!/usr/bin/env bash
# One-time Droplet hardening (Ubuntu 24.04). Run as root:  bash server_setup.sh <your-ssh-public-key-file>
set -euo pipefail
KEY_FILE="${1:?pass the path to your SSH public key}"

apt-get update && apt-get -y upgrade
apt-get install -y ca-certificates curl ufw fail2ban unattended-upgrades git
dpkg-reconfigure -f noninteractive unattended-upgrades

id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -m 600 -o deploy -g deploy "$KEY_FILE" /home/deploy/.ssh/authorized_keys
echo "deploy ALL=(ALL) NOPASSWD:/usr/bin/docker, /usr/bin/systemctl" > /etc/sudoers.d/deploy && chmod 440 /etc/sudoers.d/deploy

cat > /etc/ssh/sshd_config.d/90-afrovending.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
AllowUsers deploy
EOF
systemctl reload ssh

ufw default deny incoming && ufw default allow outgoing
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp
ufw --force enable
systemctl enable --now fail2ban

curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
cat > /etc/docker/daemon.json <<'EOF'
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" }, "live-restore": true }
EOF
systemctl restart docker

fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab || true
echo "Done. Log in again as: ssh deploy@<droplet-ip>"
