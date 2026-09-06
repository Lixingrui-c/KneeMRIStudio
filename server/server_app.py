from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
import os
import shutil
import uuid
from pathlib import Path
import uvicorn

# 导入 nnU-Net 推理服务
from nnunet_segment import predictor_service

app = FastAPI(title="Knee MRI Segmentation API", version="1.0")

# 配置
INPUT_DIR = "temp/input"
OUTPUT_DIR = "temp/output"
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 挂载静态文件目录，供下载结果
app.mount("/static", StaticFiles(directory=OUTPUT_DIR), name="static")

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    """
    上传 .nii.gz 文件，返回分割结果的下载链接
    """
    # 验证文件格式
    if not file.filename.endswith('.nii.gz'):
        raise HTTPException(400, "仅支持 .nii.gz 格式")
    
    # 保存输入文件
    case_id = str(uuid.uuid4())
    input_path = os.path.join(INPUT_DIR, f"{case_id}_0000.nii.gz")
    
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # 执行分割
    try:
        result_files = predictor_service.predict_from_files(
            [[input_path]],  # nnU-Net 要求的格式
            OUTPUT_DIR
        )
    except Exception as e:
        raise HTTPException(500, f"分割失败: {str(e)}")
    finally:
        # 清理输入文件
        if os.path.exists(input_path):
            os.remove(input_path)
    
    # 4. 返回结果
    if not result_files:
        raise HTTPException(500, "未生成分割结果")
    
    result_path = result_files[-1]
    file_name = os.path.basename(result_path)
    
    return {
        "url": f"http://127.0.0.1:8000/static/{file_name}"
    }

@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("server_app:app", host="0.0.0.0", port=8000)