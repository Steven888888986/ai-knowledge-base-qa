"""Record real local HTTP calls, then render their evidence as a silent MP4."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "docs/evidence/demo-api.json"
VIDEO = ROOT / "presentation/AI领域知识库问答系统-API操作实录.mp4"
BUILD = ROOT / ".tmp/demo-video"


def now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def record():
    sample = {"title": "AI 知识样本：RAG", "source": "demo://ai-rag-basics",
              "content": "检索增强生成（RAG）先从外部知识库检索相关片段，再把片段交给语言模型生成回答。RAG 回答应显示来源与原文片段，证据不足时明确拒答。"}
    log = {"schema": "kbqa-api-demo-v1", "recorded_at": now(),
           "recording_type": "Real HTTP request log, rendered as video; not a UI screen recording",
           "database": "Temporary isolated empty SQLite database; no seed data",
           "requests": []}
    environment = os.environ.copy()
    environment.update(OPENAI_BASE_URL="http://127.0.0.1:8081/v1", OPENAI_MODEL="local-qwen",
                       KBQA_EMBEDDING_URL="http://127.0.0.1:8082/v1/embeddings",
                       KBQA_EMBEDDING_MODEL="bge-small-zh", KBQA_LLM_ENABLED="1",
                       KBQA_EMBEDDINGS_ENABLED="1", PYTHONIOENCODING="utf-8")
    environment.pop("OPENAI_API_KEY", None)
    with tempfile.TemporaryDirectory(prefix="kbqa-api-demo-") as isolated:
        environment["KBQA_DB"] = str(Path(isolated) / "demo.sqlite3")
        code = ("import server; server.app.db().close(); "
                "s=server.Server(('127.0.0.1',0),server.Handler); "
                "print(s.server_port,flush=True); s.serve_forever()")
        with (BUILD / "server.log").open("w", encoding="utf-8") as errors:
            process = subprocess.Popen([sys.executable, "-u", "-c", code], cwd=ROOT,
                                       env=environment, stdout=subprocess.PIPE, stderr=errors,
                                       text=True, encoding="utf-8",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                port = int(process.stdout.readline().strip())
                base = f"http://127.0.0.1:{port}"
                log["base_url"] = base
                steps = [("health", "GET", "/api/health", None),
                         ("ingest", "POST", "/api/ingest", sample),
                         ("answer", "POST", "/api/query", {"question": "RAG 在生成回答之前会做什么？", "retrieval_mode": "hybrid"}),
                         ("refusal", "POST", "/api/query", {"question": "明天的天气如何？", "retrieval_mode": "hybrid"})]
                for name, method, path, payload in steps:
                    request = urllib.request.Request(base + path, method=method,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None,
                        headers={"Content-Type": "application/json"})
                    entry = {"step": name, "method": method, "path": path,
                             "request": payload, "started_at": now()}
                    started = time.perf_counter()
                    with urllib.request.urlopen(request, timeout=180) as response:
                        raw = response.read().decode("utf-8")
                        entry.update(status=response.status, response=json.loads(raw), response_text=raw)
                    entry.update(finished_at=now(), wall_ms=round((time.perf_counter() - started) * 1000, 3))
                    log["requests"].append(entry)
                    print(f'{name}: HTTP {entry["status"]}, {entry["wall_ms"]} ms', flush=True)
            finally:
                process.terminate()
                process.wait(timeout=10)
                log["finished_at"] = now()
                LOG.parent.mkdir(parents=True, exist_ok=True)
                LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log


def verify(log):
    health, ingest, answer, refusal = [entry["response"] for entry in log["requests"]]
    assert health["ok"] and health["model"]["available"]
    assert health["embedding_mode"]["mode"] == "pretrained-bge"
    assert ingest["ok"] and ingest["chunks"] > 0
    assert answer["mode"] == "llm" and not answer["refused"] and answer["citations"]
    assert all(c["source"] == "demo://ai-rag-basics" and c["snippet"] for c in answer["citations"])
    assert all(f'[{c["id"]}]' in answer["answer"] for c in answer["citations"])
    assert refusal["refused"] and refusal["mode"] == "refusal" and not refusal["citations"]


def render(log, font_path, ffmpeg):
    from PIL import Image, ImageDraw, ImageFont

    fonts = {size: ImageFont.truetype(str(font_path), size) for size in (25, 29, 33, 43, 55)}
    health, ingest, answer, refusal = log["requests"]
    result = answer["response"]
    citation = result["citations"][0]
    digest = hashlib.sha256(LOG.read_bytes()).hexdigest()
    pretty = lambda value: json.dumps(value, ensure_ascii=False, indent=2)
    timing = lambda entry: f'{entry["started_at"]}   HTTP {entry["status"]}   实测 {entry["wall_ms"]:.1f} ms'
    scenes = [
        (5, "AI 领域知识库问答系统", [
            ("API 操作实录", 55, "accent"),
            ("依据真实请求日志生成", 43, "text"),
            ("临时空数据库 → 健康检查 → 导入 → Qwen 回答与引用 → 库外拒答", 33, "text"),
            ("画面是日志可视化，不是浏览器录屏；展示时长经过编排。", 29, "muted"),
            ("无旁白。各步骤保留实际时间戳与接口耗时。", 29, "muted")]),
        (8, "01  确认本地模型服务", [
            ("GET /api/health", 43, "accent"), (timing(health), 25, "muted"),
            (pretty(health["response"]), 29, "text")]),
        (10, "02  导入 AI 样本文本", [
            ("POST /api/ingest", 43, "accent"), (timing(ingest), 25, "muted"),
            ("请求正文", 29, "muted"), (pretty(ingest["request"]), 29, "text"),
            ("真实响应  " + pretty(ingest["response"]), 29, "accent")]),
        (12, "03  基于证据的 Qwen 回答", [
            ("POST /api/query", 43, "accent"), (timing(answer), 25, "muted"),
            ("问题：" + answer["request"]["question"], 33, "text"),
            ("真实响应字段摘录（完整 JSON 另附）", 29, "muted"),
            (pretty({key: result[key] for key in ["mode", "refused", "model", "elapsed_ms", "answer"]}), 33, "text")]),
        (10, "04  展开返回的引用证据", [
            (f'引用 [{citation["id"]}]  ·  {citation["title"]}', 43, "accent"),
            (f'来源  {citation["source"]}', 33, "text"),
            (f'片段编号  {citation["chunk_id"]}', 33, "text"),
            ("snippet 原文", 29, "muted"), (citation["snippet"].replace("。", "。\n").rstrip(), 43, "text"),
            ("该片段来自刚才导入的样本；引用便于回到原文核验。", 29, "muted")]),
        (10, "05  库外问题得到明确拒答", [
            ("POST /api/query", 43, "accent"), (timing(refusal), 25, "muted"),
            ("问题：" + refusal["request"]["question"], 33, "text"),
            ("真实响应字段摘录（完整 JSON 另附）", 29, "muted"),
            (pretty({key: refusal["response"][key] for key in ["mode", "refused", "citations", "elapsed_ms", "answer"]}), 33, "text")]),
        (5, "本次真实操作的证据", [
            ("4 次 HTTP 请求均已保存原始 JSON", 43, "accent"),
            ("日志：docs/evidence/demo-api.json\n复现：scripts/record_demo.py", 33, "text"),
            ("完整日志 SHA-256\n" + digest, 25, "muted"),
            ("API 操作实录（依据真实请求日志生成）", 33, "text")]),
    ]
    colors = {"text": "#EDF5FA", "muted": "#A6BACB", "accent": "#60DAC6"}
    frames = []
    for index, (seconds, title, blocks) in enumerate(scenes, 1):
        canvas = Image.new("RGB", (1920, 1080), "#0C1D2C")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 17, 1080), fill="#15A795")
        draw.text((78, 50), "API 操作实录（依据真实请求日志生成）", font=fonts[29], fill=colors["accent"])
        draw.text((78, 108), title, font=fonts[55], fill=colors["text"])
        draw.line((78, 192, 1842, 192), fill="#345064", width=2)
        y = 230
        for text, size, color in blocks:
            for paragraph in text.splitlines():
                line = ""
                for char in paragraph:
                    if line and draw.textlength(line + char, font=fonts[size]) > 1730:
                        draw.text((88, y), line, font=fonts[size], fill=colors[color])
                        y += int(size * 1.4)
                        line = ""
                    line += char
                draw.text((88, y), line, font=fonts[size], fill=colors[color])
                y += int(size * 1.4)
            y += 19
        if y > 1000:
            raise ValueError(f"Scene {index} text overflows: y={y}")
        draw.text((78, 1030), "独立临时数据库 · 本地 HTTP / Qwen / BGE · 展示节奏不代表接口耗时", font=fonts[25], fill=colors["muted"])
        draw.text((1750, 1030), f"{index:02d} / 07", font=fonts[25], fill=colors["accent"])
        frame = BUILD / f"scene-{index:02d}.png"
        canvas.save(frame)
        frames.extend([f"file '{frame.name}'", f"duration {seconds}"])
    frames.append("file 'scene-07.png'")
    (BUILD / "frames.txt").write_text("\n".join(frames) + "\n", encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", "frames.txt", "-t", "60", "-vf", "fps=24,format=yuv420p", "-c:v", "libx264",
                    "-preset", "fast", "-crf", "21", "-movflags", "+faststart", str(VIDEO)], cwd=BUILD, check=True)
    subprocess.run([ffmpeg, "-v", "error", "-i", str(VIDEO), "-f", "null", "-"], check=True)
    for second in [2, 8, 17, 28, 40, 49, 57]:
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", str(second), "-i", str(VIDEO), "-frames:v", "1",
                        str(BUILD / f"decoded-{second:02d}.png")], check=True)
    print(f"Video verified by full decode: {VIDEO}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-log", action="store_true", help="Render the existing real log without new requests")
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/Deng.ttf"))
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    args = parser.parse_args()
    if not args.ffmpeg:
        import imageio_ffmpeg
        args.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    BUILD.mkdir(parents=True, exist_ok=True)
    VIDEO.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(LOG.read_text(encoding="utf-8")) if args.reuse_log else record()
    verify(log)
    render(log, args.font, args.ffmpeg)


if __name__ == "__main__":
    main()
