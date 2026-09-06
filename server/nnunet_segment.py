import torch
from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
import os
from pathlib import Path

class NNUNetPredictorService:
    """nnU-Net 推理服务（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls) ##这里super()指基类object
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_folder = r"nnUNet_results\Dataset001_KneeSeg\nnUNetTrainer__nnUNetPlans__2d"
        
        print(f"加载模型: {self.model_folder}")
        print(f"使用设备: {self.device}")
        
        self.predictor = nnUNetPredictor(
            tile_step_size=0.5,
            use_gaussian=True,
            use_mirroring=True,
            perform_everything_on_device=True,
            device=self.device,
            verbose=False
        )
        
        self.predictor.initialize_from_trained_model_folder(
            self.model_folder,
            use_folds=(0,),
            checkpoint_name='checkpoint_final.pth'
        )
        
        print("模型加载完成!")
    
    def predict_from_files(self, input_paths, output_folder):
        """执行推理"""
        os.makedirs(output_folder, exist_ok=True)
        
        self.predictor.predict_from_files(
            input_paths,
            output_folder,
            save_probabilities=False,
            overwrite=True,
            num_processes_segmentation_export=1,
            num_processes_preprocessing=1
        )
        
        # 返回生成的文件列表
        return [str(f) for f in Path(output_folder).glob("*.nii.gz")]

# 创建全局实例（服务启动时自动初始化）
predictor_service = NNUNetPredictorService()