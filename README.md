# SakuraLLM-Sub-Translator (RTX 3060 Ti)

这是一个利用 **SakuraLLM (Qwen2.5-7B)** 大模型实现的本地字幕翻译方案。项目针对 NVIDIA RTX 30 系列显卡（以 3060 Ti 为例）进行了深度加速优化，翻译单集动漫（约 400 行）仅需 **70秒**。使用前先下载现成的日语字幕。翻译其他语言字幕请使用AI帮你修改脚本。

---

## 🚀 核心特性
## 1. 📂 双模自适应引擎 (Adaptive Dual-Mode)
脚本会根据输入文件的后缀名自动切换翻译策略：

- **SRT 模式**：采用 多线程并发 (Concurrent) 逻辑。利用多核性能，单行快速翻译，适合结构简单的文本。

- **ASS 模式**：采用 八合一批处理 (Batch-of-8) 逻辑。针对短文本进行语境增强，有效杜绝小模型在短句翻译时的“复读指令”现象。

## 2. 🛡️ ASS 特效标签原位保护
针对 ASS 字幕中复杂的样式标签（如 {\pos(x,y)\fscx50}）：

- **占位符锚定**：将标签动态转换为 AI 不可翻译的特殊标记 [T_n]。

- **物理还原**：翻译完成后，Python 会根据位置索引将标签精准填回，确保字幕颜色、位置、动态特效与原版 100% 对齐。

## 3. ➡ 跨行衔接保护技术 (Flow-Symbol Shield)
在动画字幕中，长句常被拆分为多行显示，结尾带有 ➡ 或 》 符号。

- **逻辑剥离**：脚本能识别并物理隔离行首的特殊前缀和行尾的衔接符。

- **上下文一致性**：批处理模式让 AI 感知上下句逻辑，翻译出的断句自然连贯，绝不产生重复符号。

## 4. 🧹 智能“垃圾”拦截系统
- **SKIP_LINE 机制**：自动识别纯符号、音乐行（如 ♬～），直接跳过 AI 处理，保护原有的艺术符号。

- **解析纠错**：实时清洗 AI 吐出的 ID 编号、引导语（如“翻译如下：”）及多余的括号堆叠。

---

## 📝 开发者提示
本脚本针对 3060 Ti 及以上显卡 进行了优化。

- **批处理大小 (BATCH_SIZE)**：默认为 8。如果显存充裕且追求更好的语境感，可以尝试调至 12。

- **线程数 (MAX_WORKERS)**：SRT 模式下建议设为 2-4，避免显存竞争导致报错。

更多问题请问AI。

---

## 🛠️ 技术原理
1. **文本清洗**：剥离注音（Furigana）干扰，将 敵(ヴィラン) 还原为 敵 以获取更精准的翻译语义。

2. **掩码处理**：将特效代码与正文分离，只把纯净的文本喂给 Llama-cpp。

3. **温度控制**：固定 Temperature=0.1，确保台词风格稳定，不胡言乱语。

4. **缝合还原**：将“前缀 + 翻译结果 + 后缀”进行物理拼接，生成标准 ASS 格式。

---

## 🖥️ 显示效果
<img width="1920" height="1168" alt="Snipaste_2026-02-05_17-47-18" src="https://github.com/user-attachments/assets/b7fa4059-2a68-4224-872c-3b7e704b921c" />

---

## 🖥️ 扩展插件
- **使用方法**：拖动字幕文件到播放内容中
<img width="1072" height="208" alt="image" src="https://github.com/user-attachments/assets/59d7ef04-f5d1-4de2-81f7-9b517623eee6" />

---

## 🛠️ 1. 环境准备 (必读)

要实现秒级翻译速度，必须正确配置显卡加速环境：

1. **安装驱动与工具链**：确保电脑已安装最新的 NVIDIA 驱动及 [CUDA Toolkit 12.4](https://developer.nvidia.com/cuda-12-4-0-download-archive)。
2. **安装基础依赖**：
   ```bash
   pip install pysubs2
   ```
3. **安装 CUDA 版 Llama-cpp (最关键)**： 请务必先卸载旧版本，并运行以下特定命令以启用 GPU 推理支持（针对 CUDA 12.4）：
  ```bash
  pip uninstall llama-cpp-python -y
  pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
  注意：若使用其他版本的 CUDA（如 12.1），请相应修改链接末尾的 cuXXX。
  ```
4. **python版本**: **3.11**

---

## ⚙️ 2. 脚本配置说明
在使用本项目上传的翻译脚本前，请根据你的本地环境修改以下核心变量：

- **MODEL_PATH**: .gguf 模型文件的本地绝对路径。
- **INPUT_ASS / OUTPUT_ASS**: 需要翻译的输入文件及输出结果路径。
- **BATCH_SIZE**: 推荐设置为 6，越长可能会导致越慢。
- **n_ctx**: 建议设置为 1024，可显著减少显存分配开销并大幅提升推理速度。BATCH_SIZE越高，n_ctx越大。

---

## 📈 3. 性能参考 (RTX 3060 Ti)
| 模式 | 计算核心 | 翻译一集耗时 (约400行)| 显存占用 |
| --- | --- | --- | --- |
| GPU 模式 (CUDA) | 3060 Ti 8G | ~70s | ~7.2GB |
| CPU 模式| i5 12600kf | ~20min+ | x |

---

## 🤝 鸣谢
- **模型来源**：[SakuraLLM (Qwen2.5-7B)](https://github.com/sakura-editor/sakura)
- **HuggingFace(下载模型)**: [Sakura-7B-Qwen2.5-v1.0-GGUF](https://huggingface.co/SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF/blob/main/sakura-7b-qwen2.5-v1.0-q6k.gguf)
- **底层支持**：[llama-cpp-python](https://github.com/abetlen/llama-cpp-python)与[pysubs2](https://github.com/tkarabela/pysubs2)

---

## 🤝 特别鸣谢
- **Google Gemini**：
- 提供了核心清洗逻辑的架构建议与正则优化方案。特别是在处理 ASS 样式占位符（Tag Protection）与解决本地模型 Token 溢出幻觉方面提供了关键的技术支持。
