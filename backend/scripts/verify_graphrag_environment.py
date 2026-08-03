"""Verify the Linux GraphRAG dependency group without shell quoting or stdin."""
import importlib
import sys


def main() -> int:
    modules = ("graphrag", "pyarrow", "spacy", "torch", "graspologic", "lancedb")
    for name in modules:
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            print(f"IMPORT_FAILED {name}: {type(exc).__name__}: {exc}", flush=True)
            return 1
        print(f"IMPORT_OK {name}", flush=True)
        if name == "torch":
            print(f"TORCH_PATH {getattr(module, '__file__', None)}", flush=True)
            print(f"TORCH_VERSION {getattr(module, '__version__', None)}", flush=True)
            print(f"TORCH_HAS_TENSOR {hasattr(module, 'Tensor')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
