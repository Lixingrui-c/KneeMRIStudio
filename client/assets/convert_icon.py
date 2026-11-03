from pathlib import Path
from PIL import Image, ImageOps

folder = Path(__file__).resolve().parent

with Image.open(folder / "app_icon.png") as source:
    image = source.convert("RGBA")

    # 保持比例，透明填充为正方形
    image = ImageOps.pad(
        image,
        (256, 256),
        method=Image.Resampling.LANCZOS,
        color=(0, 0, 0, 0),
    )

    image.save(
        folder / "app_icon.ico",
        format="ICO",
        sizes=[
            (16, 16), (24, 24), (32, 32),
            (48, 48), (64, 64), (128, 128), (256, 256),
        ],
    )

print("已生成：", folder / "app_icon.ico")