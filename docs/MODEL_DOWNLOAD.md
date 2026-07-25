# 模型下载

模型文件和运行产物不提交到 Git。使用统一脚本下载官方 YOLO26 权重，脚本会先保存到项目内的 `resources/offline/YOLO26-models`，再复制到运行目录 `models/pretrained`。

在项目根目录执行：

```powershell
.\scripts\download-models.ps1
```

下载多个尺寸和 ONNX：

```powershell
.\scripts\download-models.ps1 -Scales n,s -Formats pt,onnx
```

如果要把缓存放到其他磁盘，传入资源根目录：

```powershell
.\scripts\download-models.ps1 -OfflineResourceRoot 'E:\YoloResources' -Scales n,s,m
```

重复执行时脚本会复用已有文件；需要强制重新下载时添加 `-Force`。下载完成后脚本会输出每个文件的 SHA-256。SAM3 等体积很大的专用模型不由该脚本自动下载，请按其官方许可和发布渠道单独准备，并放入 `models/pretrained`。
