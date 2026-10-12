import csv
import json
import math
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from .analysis_service import DATA, run_stage

STAGES = ("segmentation", "registration", "morphometry")
tasks = {}
case_states = {}
lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    DATA.mkdir(parents=True, exist_ok=True)
    app.state.pool = ThreadPoolExecutor(max_workers=1)
    yield
    app.state.pool.shutdown(wait=True)


app = FastAPI(title="Knee MRI Analysis API", lifespan=lifespan)


def case_path(case_id):
    path = DATA / str(case_id)
    if not (path / "case.json").is_file():
        raise HTTPException(404, "病例不存在")
    if str(case_id) not in case_states:
        raise HTTPException(409, "服务已重启；本示例不恢复旧任务，请重新上传病例")
    return path


@app.post("/cases", status_code=201)
def create_case(file: UploadFile = File(...),
                knee_side: Literal["left", "right"] = Form(...)):
    if not (file.filename or "").lower().endswith(".nii.gz"):
        raise HTTPException(400, "仅支持 .nii.gz")
    case_id = str(uuid4())
    path = DATA / case_id
    (path / "input").mkdir(parents=True)
    try:
        raw = path / "input" / "image_0000.nii.gz"
        with raw.open("wb") as dst:
            shutil.copyfileobj(file.file, dst)
        import nibabel as nib
        image = nib.load(str(raw))
        if len(image.shape) != 3:
            raise ValueError("需要三维 MRI")
        # Force compressed data validation, not just header parsing.
        import numpy as np
        np.asanyarray(image.dataobj)
    except Exception as exc:
        raise HTTPException(400, f"无法读取三维 NIfTI：{exc}") from exc
    finally:
        file.file.close()
    (path / "case.json").write_text(json.dumps({
        "case_id": case_id, "knee_side": knee_side,
    }), encoding="utf-8")
    with lock:
        case_states[case_id] = {"done": set(), "active": None}
    return {"case_id": case_id, "knee_side": knee_side}


def execute_task(task_id, path, stages):
    case_id = path.name
    try:
        for stage in stages:
            with lock:
                tasks[task_id].update(status="running", stage=stage)
            run_stage(path, stage, path / f"{task_id}.log")
            with lock:
                case_states[case_id]["done"].add(stage)
        with lock:
            tasks[task_id].update(status="completed", stage=None)
    except Exception as exc:
        with lock:
            tasks[task_id].update(status="failed", error=str(exc))
    finally:
        with lock:
            case_states[case_id]["active"] = None


@app.post("/cases/{case_id}/tasks/{operation}", status_code=202)
def start_task(case_id: UUID,
               operation: Literal["segmentation", "registration", "morphometry", "analysis"],
               request: Request):
    path = case_path(case_id)
    task_id = str(uuid4())
    with lock:
        state = case_states[str(case_id)]
        if state["active"]:
            raise HTTPException(409, "该病例已有排队或运行中的任务")
        if operation == "analysis":
            # Explicitly rerun the complete pipeline; no stale cache reuse.
            stages = list(STAGES)
            state["done"].clear()
        else:
            index = STAGES.index(operation)
            if not set(STAGES[:index]).issubset(state["done"]):
                raise HTTPException(409, "请先完成此前的分割或配准步骤")
            state["done"].difference_update(STAGES[index:])
            stages = [operation]
        tasks[task_id] = {"task_id": task_id, "case_id": str(case_id),
                          "status": "queued", "stage": None, "error": None}
        state["active"] = task_id
        request.app.state.pool.submit(execute_task, task_id, path, stages)
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}")
def task_status(task_id: UUID):
    with lock:
        task = tasks.get(str(task_id))
        if task is None:
            raise HTTPException(404, "任务不存在")
        return dict(task)


ARTIFACTS = {
    "segmentation": ("segmentation", "segmentation/image.nii.gz"),
    "registration": ("registration", "registration/warped_template_seg.nii.gz"),
    "qc": ("registration", "registration/registration_qc.json"),
    "metrics": ("morphometry", "morphometry/MorphQuant.csv"),
    "compartments": ("morphometry", "morphometry/MorphQuant_Compartments.csv"),
    "areas": ("morphometry", "morphometry/FCL_Areas.csv"),
    "metadata": ("morphometry", "morphometry/MorphQuant_meta.json"),
    "femur_coverage": ("morphometry", "morphometry/femur_coverage.vtp"),
    "tibia_coverage": ("morphometry", "morphometry/tibia_coverage.vtp"),
    "bone_coverage": ("morphometry", "morphometry/bone_coverage.vtp"),
    "coverage_manifest": ("morphometry", "morphometry/coverage_manifest.json"),
}


def result_file(case_id, name):
    path = case_path(case_id)
    if name not in ARTIFACTS:
        raise HTTPException(404, "未知结果文件")
    stage, relative = ARTIFACTS[name]
    with lock:
        state = case_states[str(case_id)]
        if state["active"] or stage not in state["done"]:
            raise HTTPException(409, "结果尚未就绪")
    file = path / relative
    if not file.is_file():
        raise HTTPException(404, "结果文件不存在")
    return file


@app.get("/cases/{case_id}/files/{name}")
def download(case_id: UUID, name: str):
    file = result_file(case_id, name)
    return FileResponse(file, filename=file.name)


@app.get("/cases/{case_id}/metrics")
def metrics(case_id: UUID):
    file = result_file(case_id, "metrics")
    regions = {}
    with file.open(encoding="utf-8-sig", newline="") as src:
        for row in csv.DictReader(src):
            metric = row.pop("Row")
            for roi, text in row.items():
                value = float(text)
                regions.setdefault(roi, {})[metric] = value if math.isfinite(value) else None
    return {"case_id": str(case_id), "regions": regions,
            "units": {"FCL": "%", "Mean Thickness": "mm",
                      "Surface Area": "mm²", "Volume": "mm³"}}
