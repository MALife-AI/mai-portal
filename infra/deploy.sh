#!/bin/bash
# ─── GPU 추론 서버 배포 스크립트 ─────────────────────────────────
# 사용법: ./deploy.sh [GPU_HOST] [MODEL]
#
# 예시:
#   ./deploy.sh                          # 로컬 배포
#   ./deploy.sh gpu-server.local         # 원격 GPU 서버 배포
#   ./deploy.sh gpu-server.local 9b      # 9B 모델로 배포

set -e

GPU_HOST="${1:-localhost}"
MODEL_SIZE="${2:-4b}"

# 모델 매핑
case "$MODEL_SIZE" in
  4b)  MODEL_FILE="Qwen3.5-4B-Q8_0.gguf"; MODEL_REPO="unsloth/Qwen3.5-4B-GGUF" ;;
  9b)  MODEL_FILE="Qwen3.5-9B-Q8_0.gguf"; MODEL_REPO="unsloth/Qwen3.5-9B-GGUF" ;;
  2b)  MODEL_FILE="Qwen3.5-2B-Q8_0.gguf"; MODEL_REPO="unsloth/Qwen3.5-2B-GGUF" ;;
  *)   echo "지원 모델: 2b, 4b, 9b"; exit 1 ;;
esac

echo "=== MaLife Lake 추론 서버 배포 ==="
echo "  호스트: $GPU_HOST"
echo "  모델:   $MODEL_FILE"
echo ""

if [ "$GPU_HOST" = "localhost" ]; then
  # 로컬 배포
  echo "[1/3] 모델 다운로드..."
  mkdir -p models
  if [ ! -f "models/$MODEL_FILE" ]; then
    docker compose -f docker-compose.inference.yml --profile download run model-downloader
  else
    echo "  모델 이미 존재: models/$MODEL_FILE"
  fi

  echo "[2/3] 컨테이너 빌드..."
  MODEL_PATH="/models/$MODEL_FILE" docker compose -f docker-compose.inference.yml build inference

  echo "[3/3] 서버 시작..."
  MODEL_PATH="/models/$MODEL_FILE" docker compose -f docker-compose.inference.yml up -d inference

  echo ""
  echo "=== 배포 완료 ==="
  echo "  엔드포인트: http://localhost:8801/v1"
  echo "  헬스체크:   curl http://localhost:8801/health"
  echo ""
  echo "  .env에 추가:"
  echo "    LLAMA_SERVER_URL=http://localhost:8801/v1"
else
  # 원격 배포
  echo "[1/3] 파일 전송..."
  ssh "$GPU_HOST" "mkdir -p ~/malife-inference"
  scp Dockerfile.inference docker-compose.inference.yml "$GPU_HOST:~/malife-inference/"

  echo "[2/3] 원격 빌드 + 모델 다운로드..."
  ssh "$GPU_HOST" "cd ~/malife-inference && \
    docker compose -f docker-compose.inference.yml --profile download run model-downloader && \
    MODEL_PATH=/models/$MODEL_FILE docker compose -f docker-compose.inference.yml build inference"

  echo "[3/3] 원격 서버 시작..."
  ssh "$GPU_HOST" "cd ~/malife-inference && \
    MODEL_PATH=/models/$MODEL_FILE docker compose -f docker-compose.inference.yml up -d inference"

  echo ""
  echo "=== 원격 배포 완료 ==="
  echo "  엔드포인트: http://$GPU_HOST:8801/v1"
  echo ""
  echo "  .env에 추가:"
  echo "    LLAMA_SERVER_URL=http://$GPU_HOST:8801/v1"
fi
