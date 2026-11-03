#!/bin/bash
# 双击运行：启动本地预览服务并自动打开浏览器
cd "$(dirname "$0")"

# 找一个可用的 python3
PY=""
for p in python3 /usr/local/bin/python3 /usr/bin/python3; do
  if command -v "$p" >/dev/null 2>&1; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "未找到 python3，请安装后重试"
  read -n 1 -s -r -p "按任意键退出..."
  exit 1
fi

# 若 8765 端口已被占用（服务已在跑），直接开浏览器
if ! lsof -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  nohup "$PY" -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 &
fi

sleep 1
open "http://127.0.0.1:8765/"
echo "已在浏览器打开：http://127.0.0.1:8765/"
