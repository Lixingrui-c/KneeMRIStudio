import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
SERVER = SRC.parent
PROJECT = SERVER.parent
DATA = Path(os.environ.get("KNEE_DATA_DIR", str(SERVER / "temp" / "cases"))).resolve()
TEMPLATES = Path(os.environ.get("KNEE_TEMPLATE_DIR", str(SERVER / "templates"))).resolve()


def run_command(command, log_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT) + os.pathsep + env.get("PYTHONPATH", "")
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.run(command, cwd=SERVER, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True)


def validate_grid(reference, other):
    import nibabel as nib
    import numpy as np
    a, b = nib.load(str(reference)), nib.load(str(other))
    if len(a.shape) != 3 or a.shape != b.shape:
        raise ValueError("需要同形状的三维影像与标签")
    if not np.allclose(a.affine, b.affine, atol=1e-4, rtol=0):
        raise ValueError("影像与标签空间不一致，请先重采样")
    if a.header.get_xyzt_units()[0] != "mm" or b.header.get_xyzt_units()[0] != "mm":
        raise ValueError("本示例要求 NIfTI 明确使用 mm 空间单位")
    if not np.all(np.isfinite(a.affine)):
        raise ValueError("无效空间变换")


def run_stage(case_dir, stage, log_path):
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    raw = case_dir / "input" / "image_0000.nii.gz"
    seg = case_dir / "segmentation" / "image.nii.gz"
    reg_dir = case_dir / "registration"
    warped = reg_dir / "warped_template_seg.nii.gz"
    out = case_dir / "morphometry"

    if stage == "segmentation":
        # The existing predictor resolves its model relative to SERVER.
        # A fresh child process releases model GPU memory when this stage ends.
        code = (
            "import sys; from server.src.segment_service import predictor_service; "
            "predictor_service.predict_from_files([[sys.argv[1]]], sys.argv[2])"
        )
        run_command([sys.executable, "-c", code, str(raw), str(seg.parent)], log_path)
        if not seg.is_file():
            raise RuntimeError("未生成预期的分割文件 image.nii.gz")
        validate_grid(raw, seg)
    elif stage == "registration":
        validate_grid(raw, seg)
        template = TEMPLATES / ("KL0_R" if case["knee_side"] == "right" else "KL0_L")
        run_command([
            sys.executable, str(SRC / "morphometry" / "register_unigradicon.py"),
            "--fixed-image", str(raw), "--fixed-seg", str(seg),
            "--template-image", str(template / "KL0_template_dess.nii.gz"),
            "--template-seg", str(template / "KL0_template_seg.nii.gz"),
            "--out-dir", str(reg_dir), "--fail-on-qc",
        ], log_path)
        validate_grid(seg, warped)
    elif stage == "morphometry":
        validate_grid(seg, warped)
        out.mkdir(exist_ok=True)
        # CLI fixes the v16-final flags and writes all reporting sidecars.
        run_command([
            sys.executable, str(SRC / "morphometry" / "morphology_gpu.py"),
            "--seg", str(seg), "--registration", str(warped),
            "--knee-side", case["knee_side"],
            "--output", str(out / "MorphQuant.csv"),
            "--save-meta-json", str(out / "MorphQuant_meta.json"),
            "--export-coverage-surfaces",
        ], log_path)
        for name in ("MorphQuant.csv", "MorphQuant_Compartments.csv", "FCL_Areas.csv",
                     "MorphQuant_meta.json", "femur_coverage.vtp", "tibia_coverage.vtp",
                     "bone_coverage.vtp", "coverage_manifest.json"):
            if not (out / name).is_file() or (out / name).stat().st_size == 0:
                raise RuntimeError(f"未生成完整结果：{name}")
    else:
        raise ValueError("未知阶段")
