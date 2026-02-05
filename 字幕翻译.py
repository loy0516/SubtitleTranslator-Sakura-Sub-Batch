import re
import time
import pysubs2
from llama_cpp import Llama

# --- 配置 ---
MODEL_PATH = r"E:\Downloads\sakura-7b-qwen2.5-v1.0-q6k.gguf"
INPUT_ASS = r"E:\Downloads\[NanakoRaws] Champignon no Majo - 05 (TBS 1920x1080 x265 AAC).ass"
OUTPUT_ASS = r"E:\Downloads\output_sakura_batch.ass"
BATCH_SIZE = 10


def batch_translate():
    print("🚀 正在启动 SakuraLLM 批量翻译引擎 (GPU 加速版)...")
    # 保持 n_ctx=1024 确保 3060 Ti 运行稳健
    llm = Llama(model_path=MODEL_PATH, n_gpu_layers=-1, n_ctx=1024, verbose=False)

    subs = pysubs2.load(INPUT_ASS)
    total = len(subs)

    # 预处理：剔除 ASS 特效标签，只提取纯净的待翻译文本
    processed_lines = []
    for line in subs:
        # 使用 pysubs2 的工具剥离所有 {\...} 标签
        # 这样 (ドロシー) 前面的特效标签就不会干扰正则了
        pure_text = line.plaintext.strip()

        if not pure_text:
            processed_lines.append(None)
            continue

        # 剥离前后符号：比如把 “（ドロシー）” 拆成 “（”, “ドロシー”, “）”
        SYMBOL_RE = re.compile(r"^([^\w\u4e00-\u9fa5\u3040-\u30ff]*)[\s]*(.*?)[\s]*([^\w\u4e00-\u9fa5\u3040-\u30ff]*)$")
        match = SYMBOL_RE.match(pure_text)

        prefix, main, suffix = match.groups() if match else ("", pure_text, "")
        processed_lines.append({
            "prefix": prefix,
            "main": main,
            "suffix": suffix,
            "orig_raw": line.text  # 保留带标签的原句
        })

    time_s = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = processed_lines[i: i + BATCH_SIZE]
        to_translate = [b["main"] for b in batch if b is not None and len(b["main"]) > 0]

        if not to_translate:
            continue

        prompt_text = "\n".join([f"{idx + 1}. {text}" for idx, text in enumerate(to_translate)])
        prompt = f"<|im_start|>system\n你是一个动漫专家，请将日文台词翻译成流利的中文。按序号对应，不要多言，不要任何标点符号。<|im_end|>\n<|im_start|>user\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"

        output = llm(prompt, max_tokens=512, stop=["<|im_end|>"], echo=False)
        results = output["choices"][0]["text"].strip().split('\n')

        res_idx = 0
        for j in range(len(batch)):
            current_item = batch[j]
            if current_item and len(current_item["main"]) > 0:
                if res_idx < len(results):
                    # 1. 基础清理：去掉序号
                    clean_zh = re.sub(r'^\d+[\.、\s]*', '', results[res_idx]).strip()
                    # 2. 深度清理：去掉 AI 脑补出来的重复前缀括号
                    clean_zh = re.sub(r'^[\(\)（）「」『』\s]+', '', clean_zh)
                    # 3. 抹除末尾标点
                    clean_zh = re.sub(r'[，。！？,.\?!]+$', '', clean_zh).strip()

                    # 组装：保留原句特效标签作为第一行，干净的中文作为第二行
                    # final_zh 使用原有的 prefix/suffix，确保符号不重复
                    final_zh = f"{current_item['prefix']}{clean_zh}{current_item['suffix']}"
                    subs[i + j].text = f"{current_item['orig_raw']}\\N{final_zh}"
                    res_idx += 1
            elif current_item:
                subs[i + j].text = f"{current_item['orig_raw']}\\N{current_item['orig_raw']}"

        print(f"📈 进度: {min(i + BATCH_SIZE, total)}/{total}")

    subs.save(OUTPUT_ASS)
    time_elapsed = time.time() - time_s
    print(f"✨ 翻译完成！用时：{round(time_elapsed, 2)}s")


if __name__ == "__main__":
    batch_translate()