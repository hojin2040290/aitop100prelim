"""
GPU를 보고(A100 같은 80GB급인지, RTX 5090 같은 32GB Blackwell인지) 들어가는 조합을
원본(BF16) → FP8 → 8비트 → 4비트 순서로 하나씩 띄우고 bench.py 로 전부 측정합니다.

    python run_all.py              # 계획대로 전부 실행 (생각 모드 포함, 동시 8명)
    python run_all.py --dry-run    # 무엇을 돌리고 무엇을 건너뛸지만 보여 줌
    python run_all.py --only vllm,sglang
    python run_all.py --no-think --levels 1,2,4

결과는 bench.py 와 같은 results/bench.csv 한 파일에 쌓입니다.
  · 측정한 조합: bench.py 가 요청마다 한 줄씩 기록 (server_load_s = 서버가 뜨는 데 걸린 시간)
  · 건너뛴 조합: row_type=skipped, 이유는 error 칸
  · 실패한 조합: row_type=failed,  이유는 error 칸
자원 사용(CPU·RAM·VRAM·GPU 사용률 등)은 1초마다 results/metrics.csv 에 기록하고,
조합마다 측정 구간 요약을 bench.csv 에 row_type=resources 로 남깁니다.
모든 출력(서버 로그, 측정 진행)은 화면에 [이름] 을 붙여 그대로 보여 주고,
  results/logs/run_all.log (전체), results/logs/<엔진>-<양자화>.log (서버별) 에도 저장합니다.
"""
import argparse
import csv
import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench  # noqa: E402  (같은 폴더의 bench.py: CSV 형식과 저장 방식을 그대로 씀)
import monitor  # noqa: E402  (1초마다 CPU·RAM·VRAM·GPU 사용률 기록)
import re  # noqa: E402

W = os.environ.get("W", "/workspace")
URL = "http://127.0.0.1:8000/v1"
LOAD_TIMEOUT_S = 40 * 60      # 첫 실행은 모델 로딩·컴파일 때문에 오래 걸릴 수 있음
BENCH_TIMEOUT_S = 90 * 60

# 정밀도가 높은 것부터 (원본 → 4비트)
PLAN = [
    ("vllm", "bf16"), ("sglang", "bf16"),
    ("vllm", "fp8"), ("sglang", "fp8"),
    ("llamacpp", "q8_0"),
    ("vllm", "nvfp4"), ("sglang", "nvfp4"),
    ("llamacpp", "ud-q4_k_xl"),
]
# serve.sh 와 같은 모델: 공식 FP8, 엔진별로 검증된 NVFP4
MODEL_REPO = {
    ("vllm", "bf16"): "Qwen/Qwen3.8-27B", ("sglang", "bf16"): "Qwen/Qwen3.8-27B",
    ("vllm", "fp8"): "Qwen/Qwen3.8-27B-FP8", ("sglang", "fp8"): "Qwen/Qwen3.8-27B-FP8",
    ("vllm", "nvfp4"): "Inferact/Qwen3.8-27B-NVFP4", ("sglang", "nvfp4"): "nvidia/Qwen3.8-27B-NVFP4",
}
NEED_GB = {"bf16": 62, "fp8": 30, "q8_0": 34, "nvfp4": 22, "ud-q4_k_xl": 22}   # serve.sh 와 같은 기준
_print_lock = threading.Lock()
_run_log = None


def say(text="", **_ignored):
    """화면에 출력하고 results/logs/run_all.log 에도 같은 내용을 남김."""
    with _print_lock:
        print(text, flush=True)
        if _run_log:
            _run_log.write(text + "\n")
            _run_log.flush()


def pump(stream, prefix, extra_file=None, on_line=None):
    """하위 프로그램의 출력을 한 줄씩 받아 [prefix] 를 붙여 화면·run_all.log 에 보여 주고, 필요하면 따로 저장."""
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if extra_file:
            extra_file.write(line + "\n")
            extra_file.flush()
        if on_line:
            on_line(line)
        say(f"[{prefix}] {line}")


def step_tracker(mon):
    """bench.py 출력에서 지금 돌고 있는 테스트 이름을 읽어 감시기에 알려 줌."""
    def on_line(line):
        m = re.match(r"^\[(no-think|think)\] (\S+) 실행 중", line)
        if m:
            mon.set_step(f"{m.group(1)} {m.group(2)}")
        elif line.startswith("[동시 "):
            m = re.match(r"^\[동시 (\d+)명", line)
            mon.set_step(f"동시 {m.group(1)}명" if m else "동시 요청")
        elif line.startswith("준비 요청"):
            mon.set_step("warmup")
    return on_line


HF_HUB = os.environ.get("HF_HUB_CACHE") or os.path.join(
    os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub")


# ---------------------------------------------------------------- GPU 판단
def detect_gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,compute_cap",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    line = out.strip().splitlines()[0] if out.strip() else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 2:
        return None
    try:
        mem_gb = int(float(parts[1])) // 1024
    except ValueError:
        return None
    try:
        cc_major = int(parts[2].split(".")[0]) if len(parts) > 2 and parts[2] else 0
    except ValueError:
        cc_major = 0
    blackwell = cc_major >= 10
    if mem_gb >= 62:
        kind = "80GB급 데이터센터 GPU (A100·H100 계열): 원본 BF16 → FP8 → 8비트 → 4비트(NVFP4·Q4) 전부"
    elif mem_gb >= 36:
        kind = "40~48GB급 GPU: FP8 부터 4비트까지 가능"
    elif blackwell:
        kind = "32GB급 Blackwell GPU (RTX 5090 계열): 4비트(NVFP4·Q4)만 (FP8은 실측에서 메모리 부족으로 시작 실패)"
    else:
        kind = "32GB 이하 GPU: 4비트(NVFP4·Q4)만 가능"
    return {"name": parts[0], "mem_gb": mem_gb, "cc_major": cc_major, "blackwell": blackwell, "kind": kind}


def hf_cached(repo):
    snap = os.path.join(HF_HUB, "models--" + repo.replace("/", "--"), "snapshots")
    return bool(glob.glob(os.path.join(snap, "*", "*.safetensors")))


def skip_reason(engine, quant, gpu):
    if gpu["mem_gb"] < NEED_GB[quant]:
        return f"GPU 메모리 부족 ({gpu['mem_gb']}GB < 약 {NEED_GB[quant]}GB 필요)"
    if quant == "fp8" and gpu["mem_gb"] < 36:
        return (f"{gpu['mem_gb']}GB GPU에서는 FP8 불가 (모델 28.5GB를 올리면 남는 메모리가 거의 없어 "
                f"vLLM·SGLang 모두 시작 중 메모리 부족으로 실패한 것을 실측으로 확인)")
    if engine == "vllm" and not os.access(f"{W}/venv-vllm/bin/vllm", os.X_OK):
        return "vLLM 미설치 (bash setup.sh vllm)"
    if engine == "sglang" and not os.access(f"{W}/venv-sglang/bin/python", os.X_OK):
        return "SGLang 미설치 (bash setup.sh sglang)"
    if engine == "llamacpp":
        if not os.access(f"{W}/llama.cpp/build/bin/llama-server", os.X_OK):
            return "llama.cpp 미설치 (bash setup.sh llamacpp, nvcc 필요)"
        if not glob.glob(f"{W}/gguf/Qwen3.8-27B-{quant}.gguf") and \
                not [p for p in glob.glob(f"{W}/gguf/*.gguf") if os.path.basename(p).lower() == f"qwen3.8-27b-{quant}.gguf"]:
            return f"GGUF 파일 없음 (bash setup.sh gguf)"
    if engine != "llamacpp":
        repo = MODEL_REPO[(engine, quant)]
        if not hf_cached(repo):
            step = {"bf16": "model", "fp8": "fp8", "nvfp4": "nvfp4"}[quant]
            return f"모델 미다운로드: {repo} (bash setup.sh {step})"
    return None


# ---------------------------------------------------------------- 서버 켜기/끄기
def server_ready():
    """모델 목록이 나오고(이름이 qwen 이 아니어도 됨), /health 가 있으면 200 일 때 준비 완료로 봄.
    llama.cpp 는 모델을 불러오는 동안 /health 가 503 을 돌려줌."""
    try:
        with urllib.request.urlopen(URL + "/models", timeout=3) as r:
            if not json.loads(r.read()).get("data"):
                return False
    except Exception:
        return False
    try:
        with urllib.request.urlopen(URL.rsplit("/v1", 1)[0] + "/health", timeout=3) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 404          # /health 가 없는 엔진이면 모델 목록만으로 판단
    except Exception:
        return True


def tail(path, n=25):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except Exception:
        return ""


def gpu_used_mib():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def stop_server(proc):
    if proc.poll() is not None:
        return
    for sig, wait_s in ((signal.SIGINT, 60), (signal.SIGTERM, 30), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait_s)
            break
        except subprocess.TimeoutExpired:
            continue
    # GPU 메모리가 비워질 때까지 대기 (최대 60초). 10초 동안 줄어들지 않으면 더 기다리지 않음
    last, still = None, 0
    for _ in range(30):
        used = gpu_used_mib()
        if used is None or used < 2048:
            break
        still = still + 1 if last is not None and used >= last - 64 else 0
        if still >= 5:
            say(f"    ※ GPU 메모리가 {used}MiB 에서 더 줄지 않아 기다리지 않고 다음으로 넘어갑니다.")
            break
        last = used
        time.sleep(2)


# ---------------------------------------------------------------- 메인
def main():
    p = argparse.ArgumentParser(description="GPU에 맞는 조합을 원본부터 4비트까지 자동으로 전부 측정")
    p.add_argument("--only", default=os.environ.get("RUN_ENGINES"), help="엔진만 골라서 (예: vllm,sglang)")
    p.add_argument("--quants", default=os.environ.get("RUN_QUANTS"), help="양자화만 골라서 (예: fp8,nvfp4)")
    p.add_argument("--levels", default=os.environ.get("CONC_LEVELS", "1,2,4"),
                   help="동시 요청 단계 (기본 1,2,4). 단계마다 응답 시간이 목표 안인지 확인")
    p.add_argument("--latency-target", default=os.environ.get("LATENCY_TARGET", "15"),
                   help="답변 1건 응답 시간 목표(초, 기본 15)")
    p.add_argument("--no-think", action="store_true", help="생각 모드 테스트 생략 (빠름)")
    p.add_argument("--tests", help="bench.py 에 넘길 테스트 목록 (예: calc,inject)")
    p.add_argument("--csv", default=os.path.join(W, "results", "bench.csv"))
    p.add_argument("--dry-run", action="store_true", help="계획만 보여 주고 끝냄")
    args = p.parse_args()

    global _run_log
    log_dir = os.path.join(os.path.dirname(args.csv), "logs")
    os.makedirs(log_dir, exist_ok=True)
    _run_log = open(os.path.join(log_dir, "run_all.log"), "a", encoding="utf-8")
    say(f"===== run_all 시작 {datetime.now():%Y-%m-%d %H:%M:%S} =====")

    gpu = detect_gpu()
    if not gpu:
        sys.exit("GPU를 찾지 못했습니다. GPU 서버에서 실행하세요. (nvidia-smi 확인)")
    say(f"감지된 GPU: {gpu['name']} · {gpu['mem_gb']}GB · compute {gpu['cc_major']}.x")
    say(f"판단: {gpu['kind']}\n")

    if server_ready():
        sys.exit("이미 8000번 포트에 서버가 떠 있습니다. 그 서버를 Ctrl+C 로 끄고 다시 실행하세요.")

    plan = PLAN
    if args.only:
        want = {x.strip() for x in args.only.split(",")}
        plan = [c for c in plan if c[0] in want]
    if args.quants:
        want = {x.strip().lower() for x in args.quants.split(",")}
        plan = [c for c in plan if c[1] in want]

    steps = [(e, q, skip_reason(e, q, gpu)) for e, q in plan]
    say("실행 계획 (원본 → 4비트 순서)")
    for i, (e, q, why) in enumerate(steps, 1):
        say(f"  {i}. {e:<9} {q:<11} " + (f"건너뜀: {why}" if why else "측정"))
    todo = [s for s in steps if not s[2]]
    say(f"\n측정 {len(todo)}개 · 건너뜀 {len(steps) - len(todo)}개 "
          f"(한 조합당 대략 10~20분, 첫 조합은 컴파일 때문에 더 걸림)\n")
    if args.dry_run:
        return

    # CSV 열 구성이 예전 것과 다르면 옛 파일 이름을 바꿔 두고, 이번 실행은 모두 bench.csv 한 파일에 기록
    os.makedirs(os.path.dirname(args.csv), exist_ok=True)
    if os.path.exists(args.csv) and os.path.getsize(args.csv) > 0:
        with open(args.csv, newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f), None)
        if header != bench.COLUMNS:
            old = args.csv.replace(".csv", f"_old_{datetime.now():%Y%m%d_%H%M%S}.csv")
            os.rename(args.csv, old)
            say(f"※ 열 구성이 다른 예전 결과는 {old} 로 옮겼습니다.\n")
    out = bench.SafeCSV(args.csv)
    logs = os.path.join(os.path.dirname(args.csv), "logs")
    os.makedirs(logs, exist_ok=True)

    batch = f"{datetime.now():%Y%m%d_%H%M%S}"
    base_row = {"gpu_name": gpu["name"], "gpu_mem_total_mib": gpu["mem_gb"] * 1024,
                "host": os.uname().nodename, "started_at": datetime.now().isoformat(timespec="seconds")}

    def note(row_type, engine, quant, reason):
        out.write({**base_row, "run_id": f"{batch}_{engine}-{quant}", "label": f"{engine}-{quant}",
                   "row_type": row_type, "engine": engine, "quantization": quant,
                   "result": row_type, "error": reason})

    for e, q, why in steps:
        if why:
            note("skipped", e, q, why)

    metrics_path = os.path.join(os.path.dirname(args.csv), "metrics.csv")
    say(f"자원 기록(1초 간격): {metrics_path}\n")

    def record_resources(engine, quant, mon):
        """조합 하나가 끝나면 측정 구간의 자원 사용 요약을 bench.csv 에 한 줄로 남김."""
        sm = mon.summary("bench")
        gb = lambda mib: f"{mib / 1024:.1f}GB" if mib else "-"
        text = (f"VRAM 최대 {gb(sm['vram_peak_mib'])}/{gb(sm['vram_total_mib'])} · GPU 평균 {sm['gpu_util_avg']}% "
                f"· 전력 평균 {sm['gpu_power_avg_w']}W · 최고 {sm['gpu_temp_peak_c']}°C · CPU 평균 {sm['cpu_cores_avg']}코어 "
                f"· RAM 최대 {gb(sm['mem_peak_mib'])}")
        out.write({**base_row, "run_id": f"{batch}_{engine}-{quant}", "label": f"{engine}-{quant}",
                   "row_type": "resources", "engine": engine, "quantization": quant,
                   "gpu_mem_used_mib": sm["vram_peak_mib"], "gpu_util_pct": sm["gpu_util_avg"],
                   "total_s": sm["seconds"], "result": text, "error": json.dumps(sm, ensure_ascii=False)})
        say(f"    자원 요약 ({sm['seconds']}초): {text}")

    serve = os.path.join(HERE, "serve.sh")
    done = []

    class StartFailed(RuntimeError):
        """서버가 준비되기 전에 꺼짐 (예비 방식으로 다시 시도할 수 있는 실패)."""

    def run_combo(n, engine, quant, extra_env, tag):
        name = f"{engine}-{quant}"
        log_path = os.path.join(logs, f"{name}{tag}.log")
        say(f"[{n}/{len(todo)}] {name}: 서버 시작{' (' + tag.strip('-') + ')' if tag else ''} (로그: {log_path})", flush=True)
        env = {**os.environ, "ENGINE": engine, "QUANT": quant, "W": W, **extra_env}
        env.pop("SPEC", None)
        log = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(["bash", serve], cwd=W, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
        reader = threading.Thread(target=pump, args=(proc.stdout, f"{name} 서버", log), daemon=True)
        reader.start()
        mon = monitor.Monitor(metrics_path, name + tag, proc.pid).start()
        t0 = time.time()
        try:
            while True:
                if proc.poll() is not None:
                    raise StartFailed(f"서버가 시작 중에 종료됨 (코드 {proc.returncode})\n{tail(log_path)}")
                if server_ready():
                    break
                if time.time() - t0 > LOAD_TIMEOUT_S:
                    raise RuntimeError(f"{LOAD_TIMEOUT_S // 60}분 안에 서버가 준비되지 않음\n{tail(log_path)}")
                time.sleep(5)
            load_s = time.time() - t0
            say(f"    준비 완료 ({load_s:.0f}초). 측정 시작", flush=True)
            mon.set_phase("bench")

            cmd = [sys.executable, os.path.join(HERE, "bench.py"), "--url", URL, "--csv", args.csv,
                   "--concurrency-levels", args.levels, "--latency-target", str(args.latency_target),
                   "--server-load-s", f"{load_s:.1f}"]
            if not args.no_think:
                cmd.append("--think")
            if args.tests:
                cmd += ["--tests", args.tests]
            bp = subprocess.Popen(cmd, cwd=W, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env={**os.environ, "PYTHONUNBUFFERED": "1"})
            bt = threading.Thread(target=pump, args=(bp.stdout, f"{name} 측정", None, step_tracker(mon)), daemon=True)
            bt.start()
            try:
                rc = bp.wait(timeout=BENCH_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                bp.kill()
                raise RuntimeError(f"측정이 {BENCH_TIMEOUT_S // 60}분 안에 끝나지 않음")
            bt.join(timeout=5)
            if rc != 0:
                raise RuntimeError(f"bench.py 가 오류로 끝남 (코드 {rc})")
            done.append(name + tag)
            say(f"    완료: {name}{tag}\n", flush=True)
        except KeyboardInterrupt:
            say("\n중단합니다. 서버를 끄는 중...")
            mon.set_phase("stopping")
            stop_server(proc)
            reader.join(timeout=10)
            log.close()
            mon.stop()
            record_resources(engine, quant, mon)
            note("failed", engine, quant, "사용자가 중단함")
            sys.exit(1)
        finally:
            mon.set_phase("stopping")
            stop_server(proc)
            reader.join(timeout=10)
            if not log.closed:
                log.close()
            if mon._t.is_alive():
                mon.stop()
                record_resources(engine, quant, mon)

    for n, (engine, quant, _) in enumerate(todo, 1):
        # 32GB GPU 의 vLLM: 먼저 CUDA Graph(빠름)로 시도하고, 시작 중에 꺼지면(대개 메모리 부족) 예비 방식(--enforce-eager)으로 한 번 더
        attempts = [({}, "")]
        if engine == "vllm" and gpu["mem_gb"] < 48:
            attempts.append(({"VLLM_EAGER": "1"}, "-eager"))
        for i, (extra_env, tag) in enumerate(attempts):
            try:
                run_combo(n, engine, quant, extra_env, tag)
                break
            except StartFailed as ex:
                msg = str(ex)
                say(f"    실패: {msg.splitlines()[0]}\n    자세한 내용: {os.path.join(logs, f'{engine}-{quant}{tag}.log')}", flush=True)
                note("failed", engine, quant, (f"[{tag.strip('-')}] " if tag else "") + msg[:4000])
                if i + 1 < len(attempts):
                    say("    → CUDA Graph 로는 시작하지 못해서, 예비 방식(--enforce-eager, 느림)으로 다시 시도합니다.\n", flush=True)
                else:
                    say("")
            except Exception as ex:
                msg = str(ex)
                say(f"    실패: {msg.splitlines()[0]}\n    자세한 내용: {os.path.join(logs, f'{engine}-{quant}{tag}.log')}\n", flush=True)
                note("failed", engine, quant, (f"[{tag.strip('-')}] " if tag else "") + msg[:4000])
                break

    say(f"끝: 측정 {len(done)}개 / 계획 {len(steps)}개. 결과 파일: {args.csv}\n")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bench.compare(args.csv)
    say(buf.getvalue().rstrip())


if __name__ == "__main__":
    main()
