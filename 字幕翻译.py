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
OUTPUT_PATH = r"E:\Downloads\output_fixed.ass"

MAX_WORKERS = 2
BATCH_SIZE = 6  # ASS 专用的批处理大小
model_lock = threading.Lock()
progress_lock = threading.Lock()
completed_lines = 0
total_lines = 0

print(f"🚀 启动 SakuraLLM：双模自适应引擎...")
llm = Llama(model_path=MODEL_PATH, n_gpu_layers=-1, n_ctx=1024, verbose=False)


# --- 通用工具函数 ---

def extract_raw_japanese(text):
    """
    智能提取原文：保留所有包含日文字符的行，剔除不含日文的旧翻译行。
    """
    # 统一换行符并分割
    lines = text.replace('\\N', '\n').replace('[BR]', '\n').split('\n')
    # 筛选包含假名（平假名/片假名）的行
    jp_lines = [l.strip() for l in lines if re.search(r'[\u3040-\u30ff]', l)]

    # 如果没搜到假名（可能全是汉字），则默认取第一行
    if not jp_lines and lines:
        return lines[0].strip()

    return "\\N".join(jp_lines)


def split_prefix_properly(text):
    """提取行首名字括号/特殊符号前缀"""
    pattern = r'^((?:\{.*?\}|[-－\s]*[（\(].*?[）\)]+[\s]*|[-－]+|[^\w\u4e00-\u9fa5\u3041-\u30ff]+)+)'
    match = re.match(pattern, text)
    if match:
        prefix = match.group(1)
        body = text[len(prefix):].strip()
        return prefix, body
    return "", text


def clean_mid_text_furigana(text):
    """清理文中注音"""
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

    # 【修改点】使用智能提取函数，支持多行日文且防止重复
    original_jp = extract_raw_japanese(original_text)

    prefix, pure_body = split_prefix_properly(original_jp)
    clean_body = clean_mid_text_furigana(pure_body)

    if not clean_body.strip():
        line_obj.text = f"{original_jp}\\N{prefix}"
        return update_progress()

    prompt = f"<|im_start|>system\n你是一个日漫翻译，请将日文翻译成流利的中文台词。直接输出译文。<|im_end|>\n<|im_start|>user\n{clean_body}<|im_end|>\n<|im_start|>assistant\n"

    try:
        with model_lock:
            output = llm(prompt, max_tokens=150, stop=["<|im_end|>", "\n"], temperature=0.1, repeat_penalty=1.2)
        res = output["choices"][0]["text"].strip()

        # 结果清洗：去掉 AI 引导语、占位符碎片和孤立符号
        res = re.sub(r'翻译结果|译文|翻译[:：]|「|」', '', res).strip()
        res = re.sub(r'\[?T\d+\]?|\[T|T\]', '', res)  # 清理占位符
        res = res.replace('[', '').replace(']', '')  # 全局清理中括号
        res = re.sub(r'(^|\\N)[-－\s]+', r'\1', res)  # 清理行首横杠
        res = res.strip()

        if res:
            final_zh = f"{prefix}{res}".replace("[BR]", "\\N")
            line_obj.text = f"{original_jp}\\N{final_zh}"
        else:
            line_obj.text = f"{original_jp}\\N{prefix}{clean_body}"
        update_progress()
    except Exception:
        line_obj.text = original_jp
        update_progress()


# --- 方案 B: ASS 逻辑 (批处理保护) ---

def protect_ass_tags(text):
    """提取标签占位符，并增强行尾符号保护"""
    prefix, rem_text = split_prefix_properly(text)
    suffix_pattern = r'([➡≫》>]+)$'
    suffix_match = re.search(suffix_pattern, rem_text)
    suffix = suffix_match.group(1) if suffix_match else ""
    body = rem_text[:-len(suffix)] if suffix else rem_text

    tags = re.findall(r'\{.*?\}', body)
    masked_body = body
    for i, tag in enumerate(tags):
        masked_body = masked_body.replace(tag, f" [T{i}] ", 1)

    masked_body = clean_mid_text_furigana(masked_body)
    return prefix, masked_body, tags, suffix


def translate_batch_ass(batch_tasks):
    prompt_lines = []
    for idx, task in enumerate(batch_tasks):
        if not re.search(r'[\u3040-\u30ff\u4e00-\u9fa5]', task['masked_body']):
            prompt_lines.append(f"{idx + 1}: SKIP_LINE")
        else:
            prompt_lines.append(f"{idx + 1}: {task['masked_body']}")

    combined_input = "\n".join(prompt_lines)

    prompt = f"<|im_start|>system\n你是一个日漫翻译专家。请按编号翻译台词，保持[T_n]占位符位置不变。如果输入包含\\N换行，请对应保留。如果看到 SKIP_LINE 则原样输出。<|im_end|>\n<|im_start|>user\n{combined_input}<|im_end|>\n<|im_start|>assistant\n1: "

    with model_lock:
        output = llm(prompt, max_tokens=1024, temperature=0.1, stop=["<|im_end|>", "User:"])

    raw_res = "1: " + output["choices"][0]["text"]
    results = {}
    for i in range(len(batch_tasks)):
        pattern = rf"{i + 1}[:：]\s*(.*?)(?=\n\d+[:：]|$)"
        match = re.search(pattern, raw_res, re.DOTALL)

        if match:
            content = match.group(1).strip()

            # 1. 基础拆解：删掉 ID 和 占位符碎片
            content = re.sub(r'^\d+[:：.]\s*', '', content)
            content = re.sub(r'\[?T\d+\]?|\[T|T\]', '', content)
            content = content.replace('[', '').replace(']', '')
            content = re.sub(r'翻译结果|译文|「|」|SKIP_LINE', '', content).strip()

            # 2. 长度熔断：如果翻译比原文长 5 倍且超过 50 字，判定为百科幻觉
            # 这一步放在去重之前，因为去重后长度会变短，可能漏掉幻觉判断
            if len(content) > 50 and len(content) > len(task['masked_body']) * 5:
                # 仅保留第一句，防止百科词条占屏
                parts = re.split(r'[，。！]', content)
                content = parts[0] + "..."

            # 3. 连续复读清洗 (针对：好痛好痛好痛...)
            # 处理短语复读 (3-15个字重复3次以上)
            content = re.sub(r'(.{3,15}?)(\1){2,}', r'\1\1...', content)
            # 处理单字/短词复读 (1-3个字重复4次以上)
            content = re.sub(r'(.+?)\1{4,}', r'\1\1\1...', content)

            # 4. 尾部垃圾与数字清理
            # 删掉行尾孤立数字 (解决 2 的问题)
            content = re.sub(r'[\s\\N]*\d{1,2}$', '', content)
            # 删掉行首/换行后的横杠
            content = re.sub(r'(^|\\N)[-－\s]+', r'\1', content)

            # 5. 符号行特殊保护
            # 如果原文没汉字/假名，译文也不该有数字
            if not re.search(r'[\u3040-\u30ff\u4e00-\u9fa5]', task['masked_body']):
                content = re.sub(r'\d+', '', content)

            results[i] = content.strip()
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
            # 此处不直接分行，由翻译逻辑内部处理多行关系
            p = p.replace("\\N", "[BR]").replace("\n", "[BR]")
            all_tasks.append((line, p))

    total_lines = len(all_tasks)
    time_s = time.time()

    if ext == ".ass":
        print(f"🎬 检测到 ASS 格式，启动【批处理保护】方案...")
        ass_tasks = []
        for line_obj, text in all_tasks:
            # 【修改点】回填前先洗一遍原文，支持多行日文
            raw_jp = extract_raw_japanese(text)
            prefix, masked_body, tags, suffix = protect_ass_tags(raw_jp)
            ass_tasks.append({
                'obj': line_obj,
                'masked_body': masked_body,
                'prefix': prefix,
                'tags': tags,
                'suffix': suffix,
                'raw_jp': raw_jp
            })

        for i in range(0, total_lines, BATCH_SIZE):
            batch = ass_tasks[i: i + BATCH_SIZE]
            batch_results = translate_batch_ass(batch)
            for idx, task in enumerate(batch):
                res = batch_results.get(idx, "")
                if res:
                    for t_idx, tag in enumerate(task['tags']):
                        res = res.replace(f"[T{t_idx}]", tag).replace(f"T{t_idx}", tag)

                    res = re.sub(r'([《（(])\1+', r'\1', res)
                    final_zh = f"{task['prefix']}{res}{task['suffix']}"
                    final_zh = final_zh.replace(" ", "").replace("[BR]", "\\N")

                    # 【修改点】统一使用清洗后的 raw_jp 进行回填
                    task['obj'].text = f"{task['raw_jp']}\\N{final_zh}"
                else:
                    task['obj'].text = task['raw_jp']
            update_progress(len(batch))

    else:
        print(f"📝 检测到 SRT 格式，启动【并发单行】方案...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(lambda i: translate_line_srt(i, all_tasks), range(total_lines)))

    subs.save(OUTPUT_PATH)
    time_elapsed = time.time() - time_s
    print(f"\n✨ 处理完成！输出文件：{OUTPUT_PATH} 用时：{time_elapsed:.2f}s")


if __name__ == "__main__":
    start()
