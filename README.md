# Android 视频流传输到 Python

本项目提供了多种解决方案，用于将 Android 设备的摄像头视频流实时传输到 Python 脚本进行显示，支持 **Android应用 + USB传输** 和 **WiFi 无线传输** 两种方式。

## 📁 项目文件说明

### Android应用 (推荐方案)
- `app/` - 完整的Android应用项目
- `python_receiver.py` - Python视频流接收器

### WiFi传输方案
- `video.py` - WiFi 无线传输版本 (使用 IP Webcam)
- `video_usb.py` - USB 传输基础版本 (使用 ADB + 屏幕录制)
- `video_usb_scrcpy.py` - USB 传输高级版本 (使用 Scrcpy 实时镜像)
- `video_usb_camera.py` - USB 传输摄像头版本 (使用 ADB 端口转发 + IP Webcam)

---

## 🚀 方案一：Android应用 + USB传输 (推荐)

这是一个完整的Android应用解决方案，通过USB数据线实现摄像头视频的实时传输。

### 特性
✅ **真正的摄像头流** (非屏幕录制)  
✅ **低延迟传输** (USB连接)  
✅ **高质量视频** (可调节质量)  
✅ **实时帧率显示**  
✅ **自动ADB端口转发**  
✅ **权限自动管理**  

### 环境要求

#### Android端
- Android 7.0+ (API 24+)
- 支持USB调试的设备
- 摄像头权限

#### Python端
```bash
pip install opencv-python flask numpy
```

#### 系统要求
- ADB (Android Debug Bridge)
- USB数据线

### 使用步骤

#### 1. 准备Android设备
1. **启用开发者选项**：
   - 设置 → 关于手机 → 连续点击"版本号"7次
2. **启用USB调试**：
   - 设置 → 开发者选项 → USB调试 (开启)
3. **连接设备**：
   - 用USB数据线连接手机到电脑
   - 手机上授权USB调试

#### 2. 安装ADB
**Windows:**
```bash
# 使用Chocolatey
choco install adb

# 或下载Android SDK Platform Tools
# https://developer.android.com/studio/releases/platform-tools
```

**验证安装:**
```bash
adb version
adb devices  # 应该显示你的设备
```

#### 3. 编译并安装Android应用

**方法1 - 使用Android Studio (推荐):**
1. 用Android Studio打开项目
2. 连接Android设备
3. 点击"Run"按钮直接安装并运行

**方法2 - 命令行编译:**
```bash
# 在项目根目录执行
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

#### 4. 运行Python接收器
```bash
python python_receiver.py
```

程序会自动：
- 检查ADB连接
- 设置端口转发 (localhost:8081 -> device:8081)
- 启动Flask服务器
- 打开OpenCV显示窗口

#### 5. 开始视频传输
1. 在Android设备上打开**VideoTrans**应用
2. 授予摄像头和录音权限
3. 点击"**开始传输**"按钮
4. 视频流将在电脑上的OpenCV窗口中实时显示

### 控制说明

#### Android应用控制
- **开始/停止传输** - 控制视频流开关
- **重置计数** - 重置帧计数器
- **实时状态显示** - 显示传输状态和帧数

#### Python接收器控制
- **'q'键** - 退出程序
- **'s'键** - 保存当前帧截图
- **实时信息显示** - FPS、帧数、分辨率

### 故障排除

#### 常见问题

**1. "ADB未安装或不在PATH中"**
- 安装Android SDK Platform Tools
- 确保adb命令可在命令行中执行

**2. "未检测到连接的Android设备"**
- 检查USB连接
- 确保USB调试已启用
- 运行 `adb devices` 检查设备状态

**3. "无法连接到Python服务器"**
- 确保Python接收器正在运行
- 检查端口转发是否设置成功
- 尝试重启ADB: `adb kill-server && adb start-server`

**4. "权限被拒绝"**
- 在Android应用中重新授予摄像头权限
- 检查设备的权限设置

**5. "视频质量差或延迟高"**
- 使用更好的USB数据线
- 在Android应用中降低视频质量设置
- 确保电脑性能足够

---

## 🌐 方案二：WiFi 无线传输 (IP Webcam)

### 环境要求

#### Python依赖
```bash
pip install opencv-python requests
```

#### Android设备要求
- Android 5.0+ 系统
- 下载并安装 **IP Webcam** 应用（Google Play商店搜索"IP Webcam"）

### 使用步骤 (WiFi)

#### 1. 设置IP Webcam应用
1. 在Android设备上打开IP Webcam应用
2. 滚动到底部，点击"Start server"
3. 记录显示的IP地址 (例如: 192.168.1.100:8081)

#### 2. 运行Python脚本
```bash
python video.py
```

#### 3. 输入IP地址
- 程序会提示输入IP Webcam的地址
- 输入完整地址，如: http://192.168.1.100:8081

---

## 🔧 高级配置

### 性能优化

#### Android应用设置
- **视频质量**: 在代码中调整 `JPEG_QUALITY` (默认80)
- **最大帧大小**: 调整 `MAX_FRAME_SIZE` (默认1MB)
- **传输频率**: 修改图像分析的背压策略

#### Python接收器设置
- **端口号**: 运行时指定 `python python_receiver.py 8081`
- **显示FPS**: 调整OpenCV的waitKey延迟
- **缓冲区大小**: 修改Flask的请求处理

### 网络配置

#### USB端口转发
```bash
# 设置端口转发
adb forward tcp:8081 tcp:8081

# 查看端口转发
adb forward --list

# 移除端口转发
adb forward --remove tcp:8081
```

#### 防火墙设置
确保以下端口未被阻止：
- **8081** (默认传输端口)
- **5037** (ADB服务端口)

---

## 📊 技术细节

### 传输协议
- **Android → Python**: HTTP POST (JPEG图像)
- **连接方式**: ADB USB端口转发
- **图像格式**: JPEG压缩 (可调质量)
- **传输频率**: 实时 (取决于摄像头帧率)

### 性能指标
- **延迟**: < 100ms (USB连接)
- **带宽**: 1-5 Mbps (取决于分辨率和质量)
- **支持分辨率**: 最高1080p
- **帧率**: 最高30fps

### 架构说明
```
Android App (CameraX) 
    ↓ (JPEG frames)
VideoStreamer (OkHttp)
    ↓ (HTTP POST)
ADB Port Forward
    ↓ (localhost:8081)
Python Flask Server
    ↓ (decoded frames)
OpenCV Display
```

---

## 🛠️ 开发说明

### 项目结构
```
VideoTrans/
├── app/                          # Android应用
│   ├── src/main/java/com/example/videotrans/
│   │   ├── MainActivity.kt       # 主活动
│   │   ├── CameraPreviewScreen.kt # 摄像头预览界面
│   │   └── VideoStreamer.kt      # 视频流传输器
│   └── build.gradle.kts          # 依赖配置
├── python_receiver.py            # Python接收器
├── video.py                      # WiFi方案
└── README.md                     # 说明文档
```

### 关键组件

#### Android端
- **CameraX**: 摄像头捕获和预览
- **OkHttp**: HTTP客户端，发送图像帧
- **Jetpack Compose**: 现代UI框架
- **协程**: 异步处理和线程管理

#### Python端
- **Flask**: HTTP服务器，接收图像帧
- **OpenCV**: 图像处理和显示
- **NumPy**: 数组处理
- **Threading**: 多线程处理

### 扩展功能

可以基于此项目添加：
- **录制功能** - 保存视频文件
- **多设备支持** - 同时连接多个Android设备
- **图像处理** - 实时滤镜和效果
- **远程控制** - 从Python端控制Android摄像头
- **音频传输** - 添加音频流支持

---

## 📄 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 支持

如有问题，请：
1. 查看故障排除部分
2. 检查日志输出
3. 提交详细的Issue描述