"""
导出 bge-small-zh-v1.5 为 ONNX 格式

在有 torch + transformers 的环境中运行一次，生成 model.onnx。
生成的文件放在模型目录下，之后服务器只需 onnxruntime 即可推理。

用法：
    python -m api.export_onnx
    python -m api.export_onnx --model models/bge-small-zh-v1.5 --output models/bge-small-zh-v1.5/model.onnx
"""
import os
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "bge-small-zh-v1.5")
DEFAULT_OUTPUT = os.path.join(DEFAULT_MODEL_DIR, "model.onnx")


def export(model_dir: str, output_path: str):
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("请在有 torch + transformers 的环境中运行此脚本。")
        return

    print(f"加载模型: {model_dir}")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModel.from_pretrained(model_dir)
    model.eval()

    # 构造 dummy 输入
    dummy = tokenizer("导出测试", return_tensors="pt", padding=True, truncation=True, max_length=512)
    input_ids = dummy["input_ids"]
    attention_mask = dummy["attention_mask"]
    token_type_ids = dummy.get("token_type_ids", torch.zeros_like(input_ids))

    print(f"导出到: {output_path}")
    with torch.no_grad():
        torch.onnx.export(
            model,
            (input_ids, attention_mask, token_type_ids),
            output_path,
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["last_hidden_state", "pooler_output"],
            dynamic_axes={
                "input_ids":      {0: "batch", 1: "seq_len"},
                "attention_mask": {0: "batch", 1: "seq_len"},
                "token_type_ids": {0: "batch", 1: "seq_len"},
                "last_hidden_state": {0: "batch", 1: "seq_len"},
                "pooler_output":     {0: "batch"},
            },
            opset_version=14,
            do_constant_folding=True,
        )

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"导出完成: {output_path} ({size_mb:.1f} MB)")
    print("\n验证推理...")
    _verify(output_path, tokenizer)


def _verify(onnx_path: str, tokenizer):
    import onnxruntime as ort
    import numpy as np

    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    enc = tokenizer("验证测试", return_tensors="np", padding=True, truncation=True, max_length=512)
    outputs = session.run(None, {
        "input_ids": enc["input_ids"].astype(np.int64),
        "attention_mask": enc["attention_mask"].astype(np.int64),
        "token_type_ids": enc.get("token_type_ids", np.zeros_like(enc["input_ids"])).astype(np.int64),
    })
    cls_vec = outputs[0][0, 0, :]
    print(f"CLS 向量 shape: {cls_vec.shape}, norm: {(cls_vec**2).sum()**0.5:.4f}")
    print("验证通过！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出 bge-small-zh-v1.5 为 ONNX")
    parser.add_argument("--model", default=DEFAULT_MODEL_DIR, help="模型目录")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="输出 ONNX 路径")
    args = parser.parse_args()
    export(args.model, args.output)
