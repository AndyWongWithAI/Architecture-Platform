#!/bin/bash
# setup-cross-cloud-ssh.sh — 配置 #1 → #2 无密码 SSH(用于架构平台异地备份)
#
# 用法:bash /home/hq/projects/Architecture-Platform/deploy/setup-cross-cloud-ssh.sh
#
# 流程:
#   1. 在 #1 上生成专用密钥对 arch-platform-backup
#   2. 提示输入 #2 ubuntu 用户密码(输入不回显)
#   3. SSH 到 #2(用 ubuntu 用户),sudo 把 #1 公钥加到 /root/.ssh/authorized_keys
#   4. 清理临时密码变量
#   5. 测试 #1 root → #2 root 无密码 SSH
#
# 注意:密码不会被记录到任何文件 / shell history

set -e

HUAWEI_IP="${HUAWEI_IP:-124.71.219.208}"
TENCENT_IP="${TENCENT_IP:-81.71.132.24}"
TENCENT_USER="${TENCENT_USER:-ubuntu}"
KEY_NAME="arch-platform-backup"

echo "============================================"
echo "  #1 root → #2 root 跨云 SSH 密钥配置"
echo "  中转用户:#2 ubuntu(密码登录) + sudo"
echo "============================================"

# 1. 在 #1 上生成专用密钥对
echo ""
echo "[Step 1/5] 在 #1($HUAWEI_IP)生成密钥对 $KEY_NAME..."
ssh -o StrictHostKeyChecking=accept-new root@$HUAWEI_IP "
    if [ -f /root/.ssh/$KEY_NAME ]; then
        echo '  (密钥已存在,跳过生成)'
    else
        ssh-keygen -t ed25519 -N '' -f /root/.ssh/$KEY_NAME -C 'arch-platform-backup-from-#1'
        echo '  ✓ 密钥已生成'
    fi
"
PUB_KEY=$(ssh root@$HUAWEI_IP "cat /root/.ssh/$KEY_NAME.pub")
echo ""
echo "  #1 公钥:"
echo "  $PUB_KEY"

# 2. 读 #2 ubuntu 密码(不回显)
echo ""
echo "[Step 2/5] 请输入 #2 ubuntu 用户密码($TENCENT_USER@$TENCENT_IP,输入不回显):"
read -s -p "  #2 password: " TENCENT_PASS
echo ""

if [ -z "$TENCENT_PASS" ]; then
    echo "ERROR: 密码不能为空" >&2
    exit 1
fi

# 3. SSH 到 #2(ubuntu 用户),sudo 把 #1 公钥加到 /root/.ssh/authorized_keys
echo ""
echo "[Step 3/5] SSH 到 #2(ubuntu),sudo 把 #1 公钥加到 /root/.ssh/authorized_keys..."

# 检查 sshpass 是否装了
if ! command -v sshpass >/dev/null 2>&1; then
    echo "ERROR: WSL 需要 sshpass,请先装:sudo apt install sshpass" >&2
    exit 1
fi

sshpass -p "$TENCENT_PASS" ssh -o StrictHostKeyChecking=accept-new $TENCENT_USER@$TENCENT_IP "
    # 探测是否需要 sudo 密码
    if sudo -n true 2>/dev/null; then
        SUDO='sudo -n'
        echo '  (sudo 无需密码,直接执行)'
    else
        SUDO='sudo'
        echo '  (sudo 需要密码,会再提示一次)'
        sudo -v <<< '$TENCENT_PASS' || { echo 'ERROR: sudo 密码错误'; exit 1; }
    fi

    \$SUDO bash -c '
        mkdir -p /root/.ssh
        chmod 700 /root/.ssh
        # 先备份
        [ -f /root/.ssh/authorized_keys ] && cp /root/.ssh/authorized_keys /root/.ssh/authorized_keys.bak.\$(date +%Y%m%d)
        # 加 #1 公钥(去重)
        grep -qF \"$PUB_KEY\" /root/.ssh/authorized_keys 2>/dev/null || echo \"$PUB_KEY\" >> /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
        echo \"  ✓ /root/.ssh/authorized_keys 已更新(共 \$(wc -l < /root/.ssh/authorized_keys) 行)\"
    '
"

# 4. 清理密码变量
TENCENT_PASS=""
unset TENCENT_PASS

# 5. 测试无密码 SSH
echo ""
echo "[Step 5/5] 测试 #1 → #2 无密码 SSH..."
# 必须显式指定 -i arch-platform-backup,否则 #1 默认用 id_rsa/id_ed25519 走密码登录
RESULT=$(ssh root@$HUAWEI_IP "ssh -o StrictHostKeyChecking=accept-new -i /root/.ssh/$KEY_NAME root@$TENCENT_IP 'echo OK-FROM-\$(hostname)'")
echo "  ✓ $RESULT"

echo ""
echo "============================================"
echo "  ✅ 完成!Task #19 跨云 SSH 已配对"
echo "============================================"
echo ""
echo "下一步:在 #1 上跑一次异地备份验证"
echo "  ssh root@$HUAWEI_IP 'REMOTE_BACKUP=1 bash /opt/services/arch-platform/deploy/backup.sh'"