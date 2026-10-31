#!/usr/bin/env bash
# vast.ai(PyTorch 템플릿)에서 엔진별 설치. 엔진끼리 패키지 버전이 부딪히지 않게 각각 따로 설치합니다.
#
#   bash setup.sh auto       GPU를 보고 필요한 것만 골라 한 번에 설치 (추천)
#   bash setup.sh model      원본(BF16) 모델 Qwen/Qwen3.8-27B (약 56GB, 62GB 이상 GPU용)
#   bash setup.sh fp8        공식 FP8 모델 Qwen/Qwen3.8-27B-FP8 (약 29GB, 36GB 이상 GPU용. 32GB GPU는 실측에서 메모리 부족으로 실패)
#   bash setup.sh nvfp4      4비트 NVFP4 모델 2개 (약 17GB씩): vLLM용 Inferact/..., SGLang용 nvidia/...
#   bash setup.sh vllm       vLLM 설치          → /workspace/venv-vllm
#   bash setup.sh sglang     SGLang 설치        → /workspace/venv-sglang
#   bash setup.sh gguf       llama.cpp 용 모델 (GPU에 들어가는 것만: Q8_0 29GB, UD-Q4_K_XL 17.6GB)
#   bash setup.sh llamacpp   llama.cpp 빌드 (CUDA 컴파일러 nvcc 가 있어야 함)
#   bash setup.sh bench      bench.py / chat.py / run_all.py 실행용 패키지 (기본 환경 /venv/main)
set -euo pipefail
W="${W:-/workspace}"
VENV_MAIN="${VENV_MAIN:-/venv/main}"
MAIN_PY="$VENV_MAIN/bin/python"
HF="$VENV_MAIN/bin/hf"
STEP="${1:-}"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# GPU 정보: 이름, 메모리(GB), 계산 능력(compute capability) 앞자리. Blackwell 은 10 이상 (B200=10, RTX 5090=12)
gpu_detect() {
  local line
  line="$(nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader,nounits 2>/dev/null | head -1 || true)"
  GPU_NAME="$(echo "$line" | cut -d, -f1 | sed 's/^ *//;s/ *$//')"
  GPU_GB=$(( $(echo "$line" | cut -d, -f2 | tr -dc '0-9' || echo 0) / 1024 ))
  local cc; cc="$(echo "$line" | cut -d, -f3 | tr -d ' ')"
  GPU_CC_MAJOR="${cc%%.*}"; GPU_CC_MAJOR="${GPU_CC_MAJOR:-0}"
}

ensure_hf() {
  if [ ! -x "$HF" ]; then
    uv pip install --python "$MAIN_PY" -q "huggingface_hub[cli,hf_xet]"
  fi
}

case "$STEP" in
  auto)
    gpu_detect
    if [ "$GPU_GB" -le 0 ]; then echo "GPU를 찾지 못했습니다. (nvidia-smi 확인)"; exit 1; fi
    echo "감지된 GPU: $GPU_NAME · ${GPU_GB}GB · compute ${GPU_CC_MAJOR}.x"
    LOGS="$W/results/logs"; mkdir -p "$LOGS"
    # 모든 출력은 화면에 [작업이름] 을 붙여 그대로 보여 주고, results/logs/setup-<작업이름>.log 에도 저장
    bash "$SELF" bench 2>&1 | sed -u 's/^/[bench] /' | tee "$LOGS/setup-bench.log"
    [ "${PIPESTATUS[0]}" -eq 0 ] || { echo "bench 설치 실패: $LOGS/setup-bench.log"; exit 1; }

    # 서로 상관없는 작업은 동시에 진행 (화면에 여러 작업의 줄이 섞여 나옴, 앞의 [이름]으로 구분)
    declare -A JOBS=()
    run_group() {  # 이름, 단계들...
      local name="$1"; shift
      rm -f "$LOGS/setup-$name.status"
      {
        ( for s in "$@"; do echo "=== $s 시작"; bash "$SELF" "$s" || exit 1; done ) 2>&1
        echo $? > "$LOGS/setup-$name.status"
      } | sed -u "s/^/[$name] /" | tee "$LOGS/setup-$name.log" &
      JOBS[$name]=$!
      echo "  시작: $name ($*)"
    }
    # RUN_ENGINES / RUN_QUANTS 로 고른 엔진·양자화에 필요한 것만 설치 (비우면 전부)
    ENG="${RUN_ENGINES:-vllm,sglang,llamacpp}"; QNT="${RUN_QUANTS:-bf16,fp8,nvfp4,q8_0,ud-q4_k_xl}"
    echo "  대상 엔진: $ENG · 대상 양자화: $QNT"
    has() { [[ ",$1," == *",$2,"* ]]; }
    has "$ENG" vllm && run_group vllm vllm
    has "$ENG" sglang && run_group sglang sglang
    # 모델 다운로드: GPU에 들어가는 것만 (한 묶음에서 차례로 받아 네트워크를 나눠 쓰지 않게 함)
    MODELS=()
    if has "$QNT" bf16; then
      if [ "$GPU_GB" -ge 62 ]; then MODELS+=(model); else echo "  건너뜀: 원본 BF16 (${GPU_GB}GB GPU에는 안 들어감)"; fi
    fi
    if has "$QNT" fp8; then
      if [ "$GPU_GB" -ge 36 ]; then MODELS+=(fp8); else echo "  건너뜀: FP8 (${GPU_GB}GB GPU는 모델 28.5GB를 올리면 문맥·상태 메모리가 부족해 vLLM·SGLang 모두 시작 실패)"; fi
    fi
    has "$QNT" nvfp4 && MODELS+=(nvfp4)
    [ "${#MODELS[@]}" -gt 0 ] && run_group models "${MODELS[@]}"
    has "$ENG" llamacpp && run_group llamacpp gguf llamacpp

    FAILED=()
    for name in "${!JOBS[@]}"; do
      wait "${JOBS[$name]}" || true
      if [ "$(cat "$LOGS/setup-$name.status" 2>/dev/null)" = "0" ]; then echo "  완료: $name"
      else echo "  실패: $name → $LOGS/setup-$name.log"; FAILED+=("$name"); fi
    done
    if [ "${#FAILED[@]}" -gt 0 ]; then
      echo "일부 설치가 실패했습니다: ${FAILED[*]}. 실패한 엔진은 run_all.py 가 자동으로 건너뜁니다."
    fi
    ;;
  model)
    ensure_hf
    "$HF" download Qwen/Qwen3.8-27B
    ;;
  fp8)
    ensure_hf
    "$HF" download Qwen/Qwen3.8-27B-FP8
    ;;
  vllm)
    uv venv "$W/venv-vllm" --python 3.12 --allow-existing
    # vLLM 레시피: vLLM 0.17.0 이상 + transformers 5.8.0 이상
    uv pip install --python "$W/venv-vllm/bin/python" -U vllm "transformers>=5.8.0" --torch-backend=auto
    # 미리 컴파일된 FlashInfer 커널(flashinfer-cubin)을 같은 버전으로 설치해 서버 첫 시작 때 컴파일할 양을 줄임.
    # 없는 버전이면 건너뛰고 계속 (그때는 serve.sh 의 MAX_JOBS 제한으로 천천히 컴파일)
    FI_VER="$("$W/venv-vllm/bin/python" -c 'import importlib.metadata as m; print(m.version("flashinfer-python"))' 2>/dev/null || true)"
    if [ -n "$FI_VER" ]; then
      uv pip install --python "$W/venv-vllm/bin/python" "flashinfer-cubin==$FI_VER" \
        || echo "  참고: flashinfer-cubin $FI_VER 이 없어 건너뜀 (첫 시작 때 커널을 직접 컴파일)"
    fi
    "$W/venv-vllm/bin/vllm" --version
    ;;
  sglang)
    uv venv "$W/venv-sglang" --python 3.12 --allow-existing
    # SGLang 쿡북: uv pip install --prerelease=allow sglang (Qwen3.8 검증 버전 v0.5.19)
    uv pip install --python "$W/venv-sglang/bin/python" --prerelease=allow "sglang>=0.5.19" "transformers>=5.8.0"
    "$W/venv-sglang/bin/python" -c "import sglang; print('sglang', sglang.__version__)"
    ;;
  nvfp4)
    # 엔진별로 검증된 모델: vLLM 레시피 → Inferact, SGLang 쿡북 → nvidia
    # A100 은 SGLang 문서상 Marlin(W4A16) 방식으로 실행 가능, vLLM 은 문서 확인이 안 돼서 시도 후 결과를 기록
    ensure_hf
    ENG="${RUN_ENGINES:-vllm,sglang}"
    [[ ",$ENG," == *",vllm,"* ]] && "$HF" download Inferact/Qwen3.8-27B-NVFP4
    [[ ",$ENG," == *",sglang,"* ]] && "$HF" download nvidia/Qwen3.8-27B-NVFP4
    true
    ;;
  gguf)
    gpu_detect
    ensure_hf
    FILES=("Qwen3.8-27B-UD-Q4_K_XL.gguf")
    if [ "$GPU_GB" -ge 34 ]; then FILES=("Qwen3.8-27B-Q8_0.gguf" "${FILES[@]}"); fi
    echo "내려받을 파일 (${GPU_GB}GB GPU 기준): ${FILES[*]}"
    "$HF" download unsloth/Qwen3.8-27B-GGUF --local-dir "$W/gguf" --include "${FILES[@]}"
    ls -lh "$W/gguf"/*.gguf
    ;;
  llamacpp)
    if ! command -v nvcc >/dev/null 2>&1; then
      echo "CUDA 컴파일러(nvcc)가 없어 llama.cpp 를 GPU용으로 빌드할 수 없습니다."
      echo "이 서버에서는 llama.cpp 비교를 건너뛰세요. (vLLM·SGLang 비교는 그대로 가능)"
      exit 1
    fi
    apt-get update -qq && apt-get install -y -qq build-essential cmake git libcurl4-openssl-dev >/dev/null
    [ -d "$W/llama.cpp" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$W/llama.cpp"
    cmake "$W/llama.cpp" -B "$W/llama.cpp/build" -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON
    cmake --build "$W/llama.cpp/build" --config Release -j --target llama-server
    "$W/llama.cpp/build/bin/llama-server" --version
    ;;
  bench)
    uv pip install --python "$MAIN_PY" openai fastapi uvicorn httpx
    ;;
  *)
    sed -n '2,13p' "$SELF"
    exit 1
    ;;
esac
echo "완료: $STEP"
