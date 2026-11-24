"""Download pinned CPU runtime and trained models; verify every SHA-256."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    (".runtime/llama-cpu.zip", "https://github.com/ggml-org/llama.cpp/releases/download/b12675/llama-b12675-bin-win-cpu-x64.zip", "bc362be03528651701e6218672bb0cbf48b55ba7acad0eb5006449567f4cf821"),
    ("models/qwen2.5-1.5b-instruct-q4_k_m.gguf", "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf", "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"),
    ("models/bge-small-zh-v1.5-q8_0.gguf", "https://huggingface.co/CompendiumLabs/bge-small-zh-v1.5-gguf/resolve/5bf683e6a1bd454bbb60ba051088c50731d63fcb/bge-small-zh-v1.5-q8_0.gguf", "5a88d266870fbd27c6f329df60de80e2d4cf3bbd5e6f080bd5c1b2e5abb12039"),
]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(asset):
    name, url, expected = asset
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and sha256(path) == expected:
        print(f"VERIFIED {name}", flush=True)
        return
    partial = path.with_suffix(path.suffix + ".part")
    print(f"DOWNLOADING {name}", flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
        received = 0
        last = 0
        while block := response.read(1024 * 1024):
            output.write(block)
            received += len(block)
            if received - last >= 100 * 1024 * 1024:
                print(f"{name}: {received // 1048576} MiB", flush=True)
                last = received
    actual = sha256(partial)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {name}: {actual}")
    partial.replace(path)
    print(f"VERIFIED {name}", flush=True)


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, ASSETS))
    runtime = ROOT / ".runtime" / "llama"
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(ROOT / ".runtime" / "llama-cpu.zip") as archive:
        archive.extractall(runtime)
    report = [{"path": name, "url": url, "sha256": checksum} for name, url, checksum in ASSETS]
    (ROOT / ".runtime" / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("READY: CPU runtime, Qwen generator, BGE Chinese embeddings", flush=True)
