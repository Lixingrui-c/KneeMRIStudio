import requests
import os
from pathlib import Path

def predict(file_path, server_url="http://127.0.0.1:8000"):
    """
    调用分割 API,上传文件并获取结果 URL
    
    Args:
        file_path: 本地 .nii.gz 文件路径
        server_url: 服务器地址，默认本地
    
    Returns:
        dict: {"url": "http://127.0.0.1:8000/static/xxx.nii.gz"}
    
    Raises:
        Exception: 请求失败时抛出
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 检查文件格式
    if not file_path.endswith('.nii.gz'):
        raise ValueError("仅支持 .nii.gz 格式的文件")
    
    url = f"{server_url}/predict"
    
    try:
        # 发送 POST 请求上传文件
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(url, files=files, timeout=300)  # 5分钟超时
        
        # 检查响应状态
        if response.status_code == 200:
            return response.json()
        else:
            # 尝试获取错误详情
            try:
                error_detail = response.json()
                raise Exception(f"API 错误: {error_detail.get('detail', response.text)}")
            except:
                raise Exception(f"API 错误: {response.status_code} - {response.text}")
                
    except requests.exceptions.ConnectionError:
        raise ConnectionError("无法连接到分割服务，请确保服务已启动")
    except requests.exceptions.Timeout:
        raise TimeoutError("分割请求超时(超过5分钟)")
    except Exception as e:
        raise Exception(f"请求失败: {str(e)}")

def download_file(url, save_path):
    """
    下载分割结果文件
    
    Args:
        url: 文件下载链接
        save_path: 保存路径
    
    Returns:
        str: 实际保存的文件路径
    """
    # 确保目录存在
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    
    try:
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()  # 检查 HTTP 状态
        
        # 流式下载，避免内存占用过大
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return save_path
        
    except requests.exceptions.ConnectionError:
        raise ConnectionError(f"无法连接到服务器: {url}")
    except requests.exceptions.Timeout:
        raise TimeoutError(f"下载超时: {url}")
    except Exception as e:
        raise Exception(f"下载失败: {str(e)}")

def predict_and_download(file_path, save_dir="seg_result", server_url="http://127.0.0.1:8000"):
    """
    一键执行分割并下载结果
    
    Args:
        file_path: 输入文件路径
        save_dir: 结果保存目录
        server_url: 服务器地址
    
    Returns:
        str: 下载的分割文件路径
    """
    # 1. 调用分割
    result = predict(file_path, server_url)
    
    # 2. 获取下载 URL
    url = result.get("url")
    if not url:
        raise Exception("API 响应中缺少 url 字段")
    
    # 3. 生成保存路径（保留原文件名）
    original_name = os.path.basename(file_path)
    # 移除 _0000 后缀（如果有）
    if original_name.endswith("_0000.nii.gz"):
        save_name = original_name.replace("_0000.nii.gz", ".nii.gz")
    else:
        save_name = f"seg_{original_name}"
    
    save_path = os.path.join(save_dir, save_name)
    
    # 4. 下载文件
    return download_file(url, save_path)