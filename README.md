# SakuraLLM-Sub-Translator (自用显卡RTX 3060 Ti)

这是一个利用 **SakuraLLM (Qwen2.5-7B)** 大模型实现的本地字幕翻译方案。项目针对 NVIDIA RTX 30 系列显卡（以 3060 Ti 为例）进行了深度加速优化，翻译单集动漫（约 400 行）仅需 **70-80 秒**。

---

## 🚀 核心特性
- **极致性能**：启用 CUDA 环境，翻译效率较 CPU 模式提升约 15 倍。
- **特效保护**：自动识别并剥离 ASS 字幕中的 `{\pos...}`、`{\fscx...}` 等特效标签，翻译后原样还原，不破坏原字幕排版。
- **智能 Batch 处理**：采用 10 行/组的批量模式，兼顾推理速度与剧情上下文的连贯性。

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
- **BATCH_SIZE**: 推荐设置为 10，这是 3060 Ti 兼顾显存占用与语境理解能力的“甜点位”。
- **n_ctx**: 建议设置为 1024，可显著减少显存分配开销并大幅提升推理速度。

---

## 📈 3. 性能参考 (RTX 3060 Ti)
| 模式 | 计算核心 | 翻译一集耗时 (约400行)| 显存占用 |
| --- | --- | --- | --- |
| GPU 模式 (CUDA) | 3060 Ti 8G | ~80s | ~7.2GB |
| CPU 模式| i5 12600kf | ~20min+ |  |

---

## 🤝 鸣谢
- **模型来源**：[SakuraLLM (Qwen2.5-7B)](https://github.com/sakura-editor/sakura)
- **HuggingFace(下载模型)**: [Sakura-7B-Qwen2.5-v1.0-GGUF](https://huggingface.co/SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF/blob/main/sakura-7b-qwen2.5-v1.0-q6k.gguf)
- **底层支持**：[llama-cpp-python](https://github.com/abetlen/llama-cpp-python)与[pysubs2](https://github.com/tkarabela/pysubs2)
