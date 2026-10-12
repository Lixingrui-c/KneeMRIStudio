from pathlib import Path

import requests


LOCAL_URL = "http://127.0.0.1:8000"

OPERATIONS = {
    "segmentation",
    "registration",
    "morphometry",
    "analysis",
}

# 当前服务端 ARTIFACTS 支持的下载名称
RESULT_FILES = {
    "bone_coverage": "bone_coverage.vtp",
    "coverage_manifest": "coverage_manifest.json",
    "segmentation": "segmentation.nii.gz",
    "registration": "warped_template_seg.nii.gz",
    "qc": "registration_qc.json",
    "metrics": "MorphQuant.csv",
    "compartments": "MorphQuant_Compartments.csv",
    "areas": "FCL_Areas.csv",
    "metadata": "MorphQuant_meta.json",
}


class APIError(RuntimeError):
    """服务端请求失败。"""


def _url(server_url, endpoint):
    return f"{server_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _check_response(response):
    """统一处理 HTTP 错误，接受所有成功状态码。"""
    if 200 <= response.status_code < 300:
        return

    try:
        payload = response.json()
    except ValueError:
        detail = response.text
    else:
        detail = (
            payload.get("detail", payload)
            if isinstance(payload, dict)
            else payload
        )

    raise APIError(
        f"HTTP {response.status_code}：{detail}"
    )


def _request_json(method, url, **kwargs):
    """发送请求并读取 JSON；异常交给调用方处理。"""
    try:
        with requests.request(method, url, **kwargs) as response:
            _check_response(response)

            try:
                return response.json()
            except ValueError as exc:
                raise APIError("服务器返回的内容不是有效 JSON") from exc

    except requests.Timeout as exc:
        raise APIError(
            "请求超时。若正在上传或提交任务，服务器可能已收到请求，"
            "请先确认状态，避免重复提交。"
        ) from exc

    except requests.ConnectionError as exc:
        raise APIError(
            "无法连接服务器，请检查服务是否启动及服务器地址是否正确"
        ) from exc

    except requests.RequestException as exc:
        raise APIError(f"网络请求失败：{exc}") from exc


def upload_case(file_path, knee_side, server_url=LOCAL_URL):
    """上传 MRI 和左右膝信息，返回包含 case_id 的字典。"""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")

    if not path.name.lower().endswith(".nii.gz"):
        raise ValueError("仅支持 .nii.gz 格式")

    if knee_side not in {"left", "right"}:
        raise ValueError("knee_side 必须是 left 或 right")

    with path.open("rb") as file:
        return _request_json(
            "POST",
            _url(server_url, "/cases"),
            files={
                "file": (
                    path.name,
                    file,
                    "application/octet-stream",
                )
            },
            data={"knee_side": knee_side},
            timeout=(10, 300),
        )


def start_task(case_id, operation, server_url=LOCAL_URL):
    """提交任务，返回 task_id；此请求不等待算法运行结束。"""
    if operation not in OPERATIONS:
        raise ValueError(
            f"不支持的任务类型：{operation}"
        )

    # case_id 和 operation 已在 URL 中，不需要再传表单。
    return _request_json(
        "POST",
        _url(server_url, f"/cases/{case_id}/tasks/{operation}"),
        timeout=(10, 30),
    )


def get_task(task_id, server_url=LOCAL_URL):
    """查询任务状态：queued / running / completed / failed。"""
    return _request_json(
        "GET",
        _url(server_url, f"/tasks/{task_id}"),
        timeout=(10, 30),
    )


def get_metrics(case_id, server_url=LOCAL_URL):
    """获取 20 区指标 JSON，适合直接填入 UI 表格。"""
    return _request_json(
        "GET",
        _url(server_url, f"/cases/{case_id}/metrics"),
        timeout=(10, 30),
    )


def download_result(
    case_id,
    name,
    save_dir="cache",
    server_url=LOCAL_URL,
):
    """
    下载结果文件，返回本地绝对路径。

    默认保存到：
        cache/病例ID/文件名
    """
    if name not in RESULT_FILES:
        raise ValueError(
            f"未知下载类型：{name}，"
            f"可选：{', '.join(RESULT_FILES)}"
        )

    # 病例 ID 作为本地目录名，验证它确实是 UUID。
    from uuid import UUID
    safe_case_id = str(UUID(str(case_id)))

    directory = Path(save_dir).resolve() / safe_case_id
    directory.mkdir(parents=True, exist_ok=True)

    target = directory / RESULT_FILES[name]

    # 先下载为临时文件，避免中途失败留下看似完整的结果。
    from uuid import uuid4
    temporary = directory / f"{target.name}.{uuid4().hex}.part"

    url = _url(
        server_url,
        f"/cases/{safe_case_id}/files/{name}",
    )

    try:
        with requests.get(
            url,
            stream=True,
            timeout=(10, 120),
        ) as response:
            _check_response(response)

            with temporary.open("wb") as file:
                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):
                    if chunk:
                        file.write(chunk)

        temporary.replace(target)
        return str(target)

    except requests.RequestException as exc:
        raise APIError(f"下载失败：{exc}") from exc

    finally:
        if temporary.exists():
            temporary.unlink()
