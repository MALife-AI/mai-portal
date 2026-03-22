"""MaLife Bare-metal Agent — 베어메탈 호스트에 설치하는 경량 관리 데몬.

기능:
  - GPU/CPU/메모리/디스크 실시간 상태 조회
  - Docker 컨테이너 기반 추론 서버 생성/중지/로그
  - 모델 파일 목록 조회

실행:
  pip install fastapi uvicorn docker psutil
  uvicorn infra.agent.server:app --host 0.0.0.0 --port 9090
"""
from __future__ import annotations

import logging
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="MaLife Bare-metal Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── 설정 ──────────────────────────────────────────────────────────────────────

MODELS_DIR = Path(os.environ.get("MODELS_DIR", str(Path.home() / ".cache/huggingface/hub")))
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "mai-agent-secret")

# ─── 인증 ──────────────────────────────────────────────────────────────────────

from fastapi import Depends, Header

async def verify_token(authorization: str = Header("")):
    if AGENT_TOKEN and authorization != f"Bearer {AGENT_TOKEN}":
        raise HTTPException(401, "Invalid agent token")

# ─── GPU 유틸 ──────────────────────────────────────────────────────────────────

def _get_gpu_info() -> list[dict[str, Any]]:
    """nvidia-smi로 GPU 정보를 조회합니다."""
    import shutil
    if not shutil.which("nvidia-smi"):
        return []
    try:
        import subprocess as _sp
        result = _sp.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 7:
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_total_mb": int(parts[2]),
                    "memory_used_mb": int(parts[3]),
                    "memory_free_mb": int(parts[4]),
                    "utilization_pct": int(parts[5]),
                    "temperature_c": int(parts[6]),
                })
        return gpus
    except Exception:
        return []

# ─── Docker 유틸 ──────────────────────────────────────────────────────────────

def _get_docker_client():
    try:
        import docker
        return docker.from_env()
    except Exception:
        return None

# ─── API: 시스템 상태 ──────────────────────────────────────────────────────────

@app.get("/status", dependencies=[Depends(verify_token)])
async def get_status() -> dict[str, Any]:
    """호스트 전체 리소스 상태를 반환합니다."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_freq = psutil.cpu_freq()

    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": {
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "percent": psutil.cpu_percent(interval=0.5),
            "freq_mhz": int(cpu_freq.current) if cpu_freq else 0,
        },
        "memory": {
            "total_gb": round(mem.total / 1e9, 1),
            "used_gb": round(mem.used / 1e9, 1),
            "free_gb": round(mem.available / 1e9, 1),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1e9, 1),
            "used_gb": round(disk.used / 1e9, 1),
            "free_gb": round(disk.free / 1e9, 1),
            "percent": round(disk.used / disk.total * 100, 1),
        },
        "gpus": _get_gpu_info(),
    }

# ─── API: 머신(컨테이너) 관리 ──────────────────────────────────────────────────

class MachineCreateRequest(BaseModel):
    name: str = Field(..., description="머신 이름 (컨테이너명)")
    model_path: str = Field(..., description="모델 파일 경로 (호스트 내)")
    model_alias: str = Field(default="model", description="모델 별칭")
    port: int = Field(default=8801, ge=1024, le=65535)
    ctx_size: int = Field(default=16384)
    n_gpu_layers: int = Field(default=999)
    cpus: float = Field(default=4.0, description="CPU 코어 수")
    memory_gb: float = Field(default=16.0, description="메모리 제한 (GB)")
    gpu_device: str = Field(default="all", description="GPU 장치 (all, 0, 1, ...)")
    extra_args: str = Field(default="", description="추가 llama-server 인자")


@app.get("/machines", dependencies=[Depends(verify_token)])
async def list_machines() -> dict[str, Any]:
    """실행 중인 추론 서버 컨테이너 목록을 반환합니다."""
    client = _get_docker_client()
    if not client:
        return {"machines": [], "error": "Docker not available"}

    machines = []
    for c in client.containers.list(all=True, filters={"label": "mai.type=inference"}):
        stats = {}
        try:
            raw = c.stats(stream=False)
            # CPU 사용률 계산
            cpu_delta = raw["cpu_stats"]["cpu_usage"]["total_usage"] - raw["precpu_stats"]["cpu_usage"]["total_usage"]
            sys_delta = raw["cpu_stats"]["system_cpu_usage"] - raw["precpu_stats"]["system_cpu_usage"]
            cpu_pct = (cpu_delta / sys_delta * 100) if sys_delta > 0 else 0
            # 메모리
            mem_used = raw["memory_stats"].get("usage", 0)
            mem_limit = raw["memory_stats"].get("limit", 0)
            stats = {
                "cpu_percent": round(cpu_pct, 1),
                "memory_used_mb": round(mem_used / 1e6),
                "memory_limit_mb": round(mem_limit / 1e6),
            }
        except Exception:
            pass

        machines.append({
            "id": c.short_id,
            "name": c.name,
            "status": c.status,
            "labels": c.labels,
            "port": c.labels.get("mai.port", ""),
            "model": c.labels.get("mai.model", ""),
            "created": c.attrs.get("Created", ""),
            "stats": stats,
        })

    return {"machines": machines}


@app.post("/machines/create", dependencies=[Depends(verify_token)])
async def create_machine(req: MachineCreateRequest) -> dict[str, Any]:
    """새 추론 서버 컨테이너를 생성합니다."""
    client = _get_docker_client()
    if not client:
        raise HTTPException(500, "Docker not available")

    # 포트 충돌 체크
    for c in client.containers.list(filters={"label": "mai.type=inference"}):
        if c.labels.get("mai.port") == str(req.port):
            raise HTTPException(409, f"포트 {req.port}이 이미 사용 중입니다: {c.name}")

    # GPU 설정
    import docker.types
    gpu_opts = None
    if req.gpu_device != "none":
        device_ids = None if req.gpu_device == "all" else [req.gpu_device]
        gpu_opts = docker.types.DeviceRequest(
            device_ids=device_ids,
            capabilities=[["gpu"]],
        )

    # llama-server 명령 구성
    cmd = (
        f"llama-server "
        f"--model /models/{Path(req.model_path).name} "
        f"--alias {req.model_alias} "
        f"--ctx-size {req.ctx_size} "
        f"--n-gpu-layers {req.n_gpu_layers} "
        f"--host 0.0.0.0 --port 8080 "
        f"--jinja "
        f"{req.extra_args}"
    )

    try:
        container = client.containers.run(
            image="ghcr.io/ggml-org/llama.cpp:server",
            name=req.name,
            command=cmd,
            detach=True,
            ports={"8080/tcp": req.port},
            volumes={
                str(Path(req.model_path).parent): {"bind": "/models", "mode": "ro"},
            },
            mem_limit=f"{int(req.memory_gb * 1024)}m",
            cpuset_cpus=None,
            nano_cpus=int(req.cpus * 1e9),
            device_requests=[gpu_opts] if gpu_opts else None,
            labels={
                "mai.type": "inference",
                "mai.name": req.name,
                "mai.model": req.model_alias,
                "mai.port": str(req.port),
                "mai.ctx_size": str(req.ctx_size),
                "mai.gpu": req.gpu_device,
                "mai.cpus": str(req.cpus),
                "mai.memory_gb": str(req.memory_gb),
            },
            restart_policy={"Name": "unless-stopped"},
        )
        return {
            "status": "created",
            "id": container.short_id,
            "name": req.name,
            "port": req.port,
        }
    except Exception as e:
        raise HTTPException(500, f"컨테이너 생성 실패: {e}")


@app.post("/machines/{name}/stop", dependencies=[Depends(verify_token)])
async def stop_machine(name: str) -> dict[str, Any]:
    """컨테이너를 중지하고 제거합니다."""
    client = _get_docker_client()
    if not client:
        raise HTTPException(500, "Docker not available")
    try:
        container = client.containers.get(name)
        container.stop(timeout=10)
        container.remove()
        return {"status": "stopped", "name": name}
    except Exception as e:
        raise HTTPException(404, f"머신 '{name}'을 찾을 수 없습니다: {e}")


@app.post("/machines/{name}/restart", dependencies=[Depends(verify_token)])
async def restart_machine(name: str) -> dict[str, Any]:
    """컨테이너를 재시작합니다."""
    client = _get_docker_client()
    if not client:
        raise HTTPException(500, "Docker not available")
    try:
        container = client.containers.get(name)
        container.restart(timeout=10)
        return {"status": "restarted", "name": name}
    except Exception as e:
        raise HTTPException(404, str(e))


@app.get("/machines/{name}/logs", dependencies=[Depends(verify_token)])
async def get_machine_logs(name: str, tail: int = 100) -> dict[str, Any]:
    """컨테이너 로그를 반환합니다."""
    client = _get_docker_client()
    if not client:
        raise HTTPException(500, "Docker not available")
    try:
        container = client.containers.get(name)
        logs = container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        return {"name": name, "logs": logs}
    except Exception as e:
        raise HTTPException(404, str(e))

# ─── API: 모델 목록 ──────────────────────────────────────────────────────────

@app.get("/models", dependencies=[Depends(verify_token)])
async def list_models() -> dict[str, Any]:
    """호스트에서 사용 가능한 GGUF 모델 파일 목록을 반환합니다."""
    models = []
    for gguf in MODELS_DIR.rglob("*.gguf"):
        stat = gguf.stat()
        models.append({
            "path": str(gguf),
            "name": gguf.name,
            "size_gb": round(stat.st_size / 1e9, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    # 크기 순 정렬
    models.sort(key=lambda m: m["size_gb"], reverse=True)
    return {"models": models, "models_dir": str(MODELS_DIR)}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "malife-bare-metal", "version": "1.0.0"}
