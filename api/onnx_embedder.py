"""
ONNX Embedding 推理器 - 替代 sentence-transformers，无需 torch

用法：
    from api.onnx_embedder import OnnxEmbedder
    model = OnnxEmbedder("/path/to/model_dir")
    vecs = model.encode(["文本1", "文本2"], normalize_embeddings=True)

模型目录需包含：
    - tokenizer.json
    - model.onnx（由 export_onnx.py 生成）
"""
import os
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class OnnxEmbedder:
    """
    基于 onnxruntime 的句子向量编码器。
    兼容 SentenceTransformer.encode() 接口（subset）。
    使用 CLS token 作为句子表示（bge-small-zh-v1.5 默认）。
    """

    def __init__(self, model_dir: str):
        onnx_path = os.path.join(model_dir, "model.onnx")
        tokenizer_path = os.path.join(model_dir, "tokenizer.json")

        if not os.path.exists(onnx_path):
            raise FileNotFoundError(
                f"ONNX 模型不存在: {onnx_path}\n"
                "请先运行 python -m api.export_onnx 导出模型。"
            )
        if not os.path.exists(tokenizer_path):
            raise FileNotFoundError(f"tokenizer.json 不存在: {tokenizer_path}")

        # 加载 tokenizer（纯 Rust，无 torch 依赖）
        self.tokenizer = Tokenizer.from_file(tokenizer_path)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=None)
        self.tokenizer.enable_truncation(max_length=512)

        # 加载 ONNX session
        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 2
        sess_opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            onnx_path,
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )

        # 检查模型输入名（兼容有无 token_type_ids）
        self._input_names = {inp.name for inp in self.session.get_inputs()}
        self._dim = 512  # bge-small-zh-v1.5

    def encode(
        self,
        sentences,
        batch_size: int = 64,
        normalize_embeddings: bool = False,
        show_progress_bar: bool = False,
        **kwargs,
    ) -> np.ndarray:
        if isinstance(sentences, str):
            sentences = [sentences]

        all_embeddings = []

        for i in range(0, len(sentences), batch_size):
            batch = sentences[i : i + batch_size]
            encoded = self.tokenizer.encode_batch(batch)

            input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

            feed = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            if "token_type_ids" in self._input_names:
                feed["token_type_ids"] = np.zeros_like(input_ids)

            outputs = self.session.run(None, feed)
            # outputs[0] = last_hidden_state (batch, seq_len, hidden)
            # CLS token pooling
            cls_embeddings = outputs[0][:, 0, :].astype(np.float32)

            if normalize_embeddings:
                norms = np.linalg.norm(cls_embeddings, axis=1, keepdims=True)
                cls_embeddings = cls_embeddings / np.maximum(norms, 1e-8)

            all_embeddings.append(cls_embeddings)

        return np.vstack(all_embeddings)

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim
