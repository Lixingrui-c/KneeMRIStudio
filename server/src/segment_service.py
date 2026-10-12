import os
from pathlib import Path


class NNUNetPredictorService:
    def __init__(self):
        import torch
        from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

        server = Path(__file__).resolve().parents[1]
        configured = os.environ.get("KNEE_MODEL_DIR")
        self.model_folder = (Path(configured) if configured else server / "nnUNet_results" / "Dataset001_KneeSeg" / "nnUNetTrainer__nnUNetPlans__2d")
        if not self.model_folder.is_absolute():
            self.model_folder = server / self.model_folder
        for relative in ("dataset.json", "plans.json", "fold_0/checkpoint_final.pth"):
            if not (self.model_folder / relative).is_file():
                raise FileNotFoundError(f"缺少 nnU-Net 模型文件：{self.model_folder / relative}")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"加载模型：{self.model_folder}；设备：{self.device}", flush=True)
        self.predictor = nnUNetPredictor(
            tile_step_size=0.5, use_gaussian=True, use_mirroring=True,
            perform_everything_on_device=self.device.type == "cuda",
            device=self.device, verbose=False,
        )
        self.predictor.initialize_from_trained_model_folder(
            str(self.model_folder), use_folds=(0,), checkpoint_name="checkpoint_final.pth"
        )
        print("模型加载完成", flush=True)

    def predict_from_files(self, input_paths, output_folder):
        output = Path(output_folder)
        output.mkdir(parents=True, exist_ok=True)
        expected = []
        for channels in input_paths:
            if not channels:
                raise ValueError("输入病例没有影像文件")
            for path in channels:
                if not Path(path).is_file():
                    raise FileNotFoundError(path)
            name = Path(channels[0]).name
            if not name.endswith("_0000.nii.gz"):
                raise ValueError("首通道文件名必须以 _0000.nii.gz 结尾")
            expected.append(output / (name[:-12] + ".nii.gz"))
        self.predictor.predict_from_files(
            input_paths, str(output), save_probabilities=False, overwrite=True,
            num_processes_segmentation_export=1, num_processes_preprocessing=1,
        )
        for path in expected:
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"未生成分割结果：{path}")
        return [str(path) for path in expected]


predictor_service = NNUNetPredictorService()
