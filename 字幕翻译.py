import time
import pysubs2
import threading
import sys
import re
import os
from llama_cpp import Llama
from concurrent.futures import ThreadPoolExecutor

# --- 配置 ---
MODEL_PATH = r"E:\Downloads\sakura-7b-qwen2.5-v1.0-q6k.gguf"
INPUT_PATH = r"E:\Downloads\INPUT_ass.ass"  # 支持 .srt 或 .ass
OUTPUT_PATH = r"E:\Downloads\output_fixedass.ass"

MAX_WORKERS = 2
BATCH_SIZE = 8  # ASS 专用的批处理大小
model_lock = threading.Lock()
progress_lock = threading.Lock()
completed_lines = 0
total_lines = 0

print(f"🚀 启动 SakuraLLM：双模自适应引擎...")
# 为了兼容批处理，n_ctx 稍微调大
llm = Llama(model_path=MODEL_PATH, n_gpu_layers=-1, n_ctx=2048, verbose=False)


# --- 通用工具函数 ---

def split_prefix_properly(text):
    """提取行首名字括号/特殊符号前缀"""
    # 增强正则：匹配行首的标签、符号、横杠或括号名
    pattern = r'^((?:\{.*?\}|[-－\s]*[（\(].*?[）\)]+[\s]*|[^\w\u4e00-\u9fa5\u3041-\u30ff]+)+)'
    match = re.match(pattern, text)
    if match:
        prefix = match.group(1)
        body = text[len(prefix):].strip()
        return prefix, body
    return "", text


def clean_mid_text_furigana(text):
    """清理文中注音，防止 AI 截断或复读"""
    return re.sub(r'([\u4e00-\u9fa5])[\(（][\u3040-\u30ff]+[\)）]', r'\1', text)


def update_progress(increment=1):
    global completed_lines
    with progress_lock:
        completed_lines += increment
        percent = (completed_lines / total_lines) * 100
        sys.stdout.write(f"\r📈 进度: {percent:.1f}% ({completed_lines}/{total_lines})")
        sys.stdout.flush()


# --- 方案 A: SRT 逻辑 (并发单行) ---

def translate_line_srt(idx, all_tasks):
    line_obj, original_text = all_tasks[idx]
    prefix, pure_body = split_prefix_properly(original_text)
    clean_body = clean_mid_text_furigana(pure_body)

    if not clean_body.strip():
        line_obj.text = f"{line_obj.text}\\N{prefix}"
        return update_progress()

    prompt = f"<|im_start|>system\n你是一个日漫翻译，请将日文翻译成流利的中文台词。直接输出译文。<|im_end|>\n<|im_start|>user\n{clean_body}<|im_end|>\n<|im_start|>assistant\n"

    try:
        with model_lock:
            output = llm(prompt, max_tokens=150, stop=["<|im_end|>", "\n"], temperature=0.1, repeat_penalty=1.2)
        res = output["choices"][0]["text"].strip()
        res = re.sub(r'^[（\(].*?[）\)]|翻译[:：]|「|」', '', res).strip()

        if res:
            final_zh = f"{prefix}{res}".replace("[BR]", "\\N")
            line_obj.text = f"{line_obj.text}\\N{final_zh}"
        else:
            line_obj.text = f"{line_obj.text}\\N{prefix}{clean_body}"
        update_progress()
    except:
        update_progress()


# --- 方案 B: ASS 逻辑 (批处理保护) ---

def protect_ass_tags(text):
    """提取标签占位符，并增强行尾符号保护"""
    # prefix, body = split_prefix_properly(text) # 旧代码

    # 新增逻辑：提取前缀的同时，提取行尾衔接符 (➡, 》, ≫, ...)
    prefix, rem_text = split_prefix_properly(text)
    suffix_pattern = r'([➡≫》>]+)$'
    suffix_match = re.search(suffix_pattern, rem_text)
    suffix = suffix_match.group(1) if suffix_match else ""
    body = rem_text[:-len(suffix)] if suffix else rem_text

    tags = re.findall(r'\{.*?\}', body)
    masked_body = body
    for i, tag in enumerate(tags):
        masked_body = masked_body.replace(tag, f" [T{i}] ", 1)

    # 同样清理注音
    masked_body = clean_mid_text_furigana(masked_body)
    return prefix, masked_body, tags, suffix


def translate_batch_ass(batch_tasks):
    prompt_lines = []
    for idx, task in enumerate(batch_tasks):
        # 增加判断：如果 masked_body 不包含任何汉字/假名（纯符号行），则标记为不需要翻译
        if not re.search(r'[\u3040-\u30ff\u4e00-\u9fa5]', task['masked_body']):
            prompt_lines.append(f"{idx + 1}: SKIP_LINE")
        else:
            prompt_lines.append(f"{idx + 1}: {task['masked_body']}")

    combined_input = "\n".join(prompt_lines)

    prompt = f"<|im_start|>system\n你是一个日漫翻译专家。请按编号翻译台词，保持[T_n]占位符位置不变。如果看到 SKIP_LINE 则原样输出。<|im_end|>\n<|im_start|>user\n{combined_input}<|im_end|>\n<|im_start|>assistant\n1: "

    with model_lock:
        output = llm(prompt, max_tokens=1024, temperature=0.1, stop=["<|im_end|>", "User:"])

    raw_res = "1: " + output["choices"][0]["text"]
    results = {}
    for i in range(len(batch_tasks)):
        pattern = rf"{i + 1}[:：]\s*(.*?)(?=\n\d+[:：]|$)"
        match = re.search(pattern, raw_res, re.DOTALL)
        if match:
            # 强化过滤：清理 ID 泄露和冗余词汇
            content = match.group(1).strip()
            content = re.sub(r'^\d+[:：]\s*', '', content)
            results[i] = re.sub(r'占位符|翻译|保持|「|」|SKIP_LINE', '', content).strip()
    return results


# --- 入口控制 ---

def start():
    global total_lines
    ext = os.path.splitext(INPUT_PATH)[1].lower()
    subs = pysubs2.load(INPUT_PATH)

    all_tasks = []
    for line in subs:
        p = line.plaintext.strip()
        if p:
            p = p.replace("\\N", "[BR]").replace("\n", "[BR]")
            all_tasks.append((line, p))

    total_lines = len(all_tasks)
    time_s = time.time()

    if ext == ".ass":
        print(f"🎬 检测到 ASS 格式，启动【批处理保护】方案 (Batch Size: {BATCH_SIZE})...")
        # 准备批处理数据
        ass_tasks = []
        for line_obj, text in all_tasks:
            # prefix, masked_body, tags = protect_ass_tags(text) # 旧代码
            prefix, masked_body, tags, suffix = protect_ass_tags(text)  # 新逻辑增加 suffix
            ass_tasks.append({
                'obj': line_obj,
                'masked_body': masked_body,
                'prefix': prefix,
                'tags': tags,
                'suffix': suffix  # 记录行尾衔接符
            })

        for i in range(0, total_lines, BATCH_SIZE):
            batch = ass_tasks[i: i + BATCH_SIZE]
            batch_results = translate_batch_ass(batch)
            for idx, task in enumerate(batch):
                res = batch_results.get(idx, "")
                if res:
                    for t_idx, tag in enumerate(task['tags']):
                        res = res.replace(f"[T{t_idx}]", tag).replace(f"T{t_idx}", tag)

                    # final_zh = f"{task['prefix']}{res}".replace(" ", "").replace("[BR]", "\\N") # 旧代码

                    # 缝合逻辑优化：去重前缀括号并粘合行尾衔接符
                    res = re.sub(r'([《（(])\1+', r'\1', res)  # 符号去重
                    final_zh = f"{task['prefix']}{res}{task['suffix']}"
                    final_zh = final_zh.replace(" ", "").replace("[BR]", "\\N")

                    task['obj'].text = f"{task['obj'].text}\\N{final_zh}"
                else:
                    task['obj'].text = f"{task['obj'].text}\\N{task['prefix']}{task['masked_body']}{task['suffix']}"
            update_progress(len(batch))

    else:
        print(f"📝 检测到 SRT 格式，启动【并发单行】方案 (Workers: {MAX_WORKERS})...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(lambda i: translate_line_srt(i, all_tasks), range(total_lines)))

    subs.save(OUTPUT_PATH)
    time_elapsed = time.time() - time_s
    print(f"\n✨ 处理完成！输出文件：{OUTPUT_PATH} 用时：{time_elapsed}s")


if __name__ == "__main__":
    start()
