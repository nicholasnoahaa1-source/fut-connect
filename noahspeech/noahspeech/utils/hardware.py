"""Hardware autodetection: CUDA > MPS > CPU, plus dtype/device selection helpers.

Works whether or not torch is installed, so the rest of the codebase (and the
test suite) can import this module in a CPU-only / torch-less sandbox and still
get a meaningful, honest answer instead of an ImportError.
"""

from __future__ import annotations

import dataclasses
import platform
import shutil
import subprocess


@dataclasses.dataclass
class HardwareInfo:
    device: str  # "cuda" | "mps" | "cpu"
    device_name: str
    torch_available: bool
    torch_version: str | None
    cuda_available: bool
    cuda_device_count: int
    mps_available: bool
    total_vram_gb: float | None
    total_ram_gb: float | None
    cpu_count: int
    platform: str
    recommended_dtype: str  # "bfloat16" | "float16" | "float32"

    def summary(self) -> str:
        lines = [
            f"device: {self.device} ({self.device_name})",
            f"platform: {self.platform}",
            f"cpu_count: {self.cpu_count}",
            f"torch_available: {self.torch_available} (version={self.torch_version})",
            f"cuda_available: {self.cuda_available} (devices={self.cuda_device_count})",
            f"mps_available: {self.mps_available}",
            f"vram_gb: {self.total_vram_gb}",
            f"ram_gb: {self.total_ram_gb}",
            f"recommended_dtype: {self.recommended_dtype}",
        ]
        return "\n".join(lines)


def _total_ram_gb() -> float | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 2)
    except OSError:
        pass
    try:
        import os

        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 2)
    except (ValueError, OSError, AttributeError):
        return None


def _nvidia_smi_vram_gb() -> float | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        mb = float(out.stdout.strip().splitlines()[0])
        return round(mb / 1024, 2)
    except (subprocess.SubprocessError, ValueError, IndexError, OSError):
        return None


def detect_hardware() -> HardwareInfo:
    """Detect the best available compute device, preferring CUDA > MPS > CPU.

    Never raises: any missing dependency (torch absent, no GPU tooling) degrades
    to CPU rather than throwing, since this is queried at process startup on
    machines that may have neither a GPU nor torch installed.
    """
    torch_available = False
    torch_version = None
    cuda_available = False
    cuda_device_count = 0
    mps_available = False
    device_name = "cpu"
    total_vram_gb = None

    try:
        import torch

        torch_available = True
        torch_version = torch.__version__
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_device_count = torch.cuda.device_count()
            device_name = torch.cuda.get_device_name(0)
            try:
                total_vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
            except (RuntimeError, AssertionError):
                total_vram_gb = _nvidia_smi_vram_gb()
        else:
            mps_available = bool(
                getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
            )
    except ImportError:
        # torch not installed in this environment: fall back to nvidia-smi so we
        # can still report whether a GPU is physically present.
        total_vram_gb = _nvidia_smi_vram_gb()
        cuda_available = total_vram_gb is not None

    if cuda_available:
        device = "cuda"
        if device_name == "cpu":
            device_name = "cuda:0 (unknown model, torch not installed)"
    elif mps_available:
        device = "mps"
        device_name = "Apple Silicon GPU (MPS)"
    else:
        device = "cpu"
        device_name = platform.processor() or platform.machine() or "cpu"

    if device == "cuda":
        recommended_dtype = "bfloat16"
    elif device == "mps":
        recommended_dtype = "float16"
    else:
        recommended_dtype = "float32"

    return HardwareInfo(
        device=device,
        device_name=device_name,
        torch_available=torch_available,
        torch_version=torch_version,
        cuda_available=cuda_available,
        cuda_device_count=cuda_device_count,
        mps_available=mps_available,
        total_vram_gb=total_vram_gb,
        total_ram_gb=_total_ram_gb(),
        cpu_count=__import__("os").cpu_count() or 1,
        platform=platform.platform(),
        recommended_dtype=recommended_dtype,
    )


def select_dtype(hw: HardwareInfo | None = None, prefer_bf16: bool = True):
    """Return the torch dtype to use given detected hardware, with FP16 fallback.

    Requires torch (raises ImportError with a clear message otherwise) since the
    return value is a torch.dtype, not something meaningfully representable
    without torch installed.
    """
    try:
        import torch
    except ImportError as e:
        raise ImportError(
            "select_dtype() requires torch to be installed; use detect_hardware() "
            "for a torch-free hardware summary."
        ) from e

    hw = hw or detect_hardware()

    if hw.device == "cuda":
        if prefer_bf16 and torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float16
    if hw.device == "mps":
        return torch.float16
    return torch.float32
