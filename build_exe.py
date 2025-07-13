#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller打包脚本
用于将gui_main.py打包成独立的exe文件
"""

import os
import sys
import shutil
from pathlib import Path

def build_exe():
    """
    使用PyInstaller打包应用程序
    """
    
    # 获取当前目录
    current_dir = Path(__file__).parent
    
    # 定义打包命令
    cmd_parts = [
        "pyinstaller",
        "--onefile",  # 打包成单个exe文件
        "--windowed",  # 不显示控制台窗口
        "--name=VideoTrans_Detection",  # 指定exe文件名
        "--icon=app.ico",  # 图标文件（如果有的话）
        
        # 添加数据文件
         "--add-data=yolo11n.pt;.",  # YOLO模型文件
         "--add-data=best.pt;.",  # 自定义训练的YOLO模型文件
         "--add-data=ultralytics;ultralytics",  # 使用本地修改过的ultralytics包
        
        # 隐藏导入（解决一些模块找不到的问题）
        "--hidden-import=ultralytics",
        "--hidden-import=ultralytics.models",
        "--hidden-import=ultralytics.models.yolo",
        "--hidden-import=ultralytics.engine",
        "--hidden-import=ultralytics.utils",
        "--hidden-import=ultralytics.nn.FRFN",
        "--hidden-import=ultralytics.nn.SEAM",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=torch",
        "--hidden-import=torchvision",
        "--hidden-import=PIL",
        "--hidden-import=flask",
        "--hidden-import=requests",
        "--hidden-import=matplotlib",
        "--hidden-import=matplotlib.pyplot",
        "--hidden-import=matplotlib.backends",
        "--hidden-import=matplotlib.backends.backend_agg",
        "--hidden-import=scipy",
        "--hidden-import=scipy.optimize",
        "--hidden-import=scipy.optimize.linear_sum_assignment",
        
        # 排除一些不需要的模块以减小文件大小
        "--exclude-module=pandas",
        "--exclude-module=jupyter",
        "--exclude-module=IPython",
        
        # 主程序文件
        "gui_main.py"
    ]
    
    # 检查必要文件是否存在
    required_files = [
        "gui_main.py",
        "tracker.py", 
        "python_receiver.py",
        "yolo11n.pt",
        "best.pt"
    ]
    
    missing_files = []
    for file in required_files:
        if not (current_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"错误：缺少必要文件: {', '.join(missing_files)}")
        return False
    
    # 创建图标文件（如果不存在）
    if not (current_dir / "app.ico").exists():
        print("警告：未找到app.ico图标文件，将使用默认图标")
        cmd_parts = [part for part in cmd_parts if not part.startswith("--icon")]
    
    # 执行打包命令
    cmd = " ".join(cmd_parts)
    print(f"使用本地ultralytics目录: {os.path.abspath('ultralytics')}")
    print(f"执行打包命令: {cmd}")
    
    result = os.system(cmd)
    
    if result == 0:
        print("\n打包成功！")
        print(f"可执行文件位置: {current_dir / 'dist' / 'VideoTrans_Detection.exe'}")
        print("\n✅ 所有文件已内嵌到exe中，无需外部依赖文件")
        
        print("\n使用说明:")
        print("1. 运行前请确保已安装必要的系统依赖（如摄像头驱动）")
        print("2. 如果使用USB手机功能，请确保ADB工具可用")
        print("3. 所有模型文件已内嵌，无需额外文件")
        
        return True
    else:
        print("\n打包失败！请检查错误信息")
        return False

def clean_build():
    """
    清理构建文件
    """
    current_dir = Path(__file__).parent
    
    # 要清理的目录和文件
    clean_targets = [
        "build",
        "dist", 
        "__pycache__",
        "*.spec"
    ]
    
    for target in clean_targets:
        if "*" in target:
            # 处理通配符
            import glob
            for file in glob.glob(str(current_dir / target)):
                try:
                    os.remove(file)
                    print(f"已删除文件: {file}")
                except Exception as e:
                    print(f"删除文件失败 {file}: {e}")
        else:
            target_path = current_dir / target
            if target_path.exists():
                try:
                    if target_path.is_dir():
                        shutil.rmtree(target_path)
                        print(f"已删除目录: {target_path}")
                    else:
                        os.remove(target_path)
                        print(f"已删除文件: {target_path}")
                except Exception as e:
                    print(f"删除失败 {target_path}: {e}")

if __name__ == "__main__":
    print("VideoTrans Detection 应用打包工具")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        print("清理构建文件...")
        clean_build()
    else:
        print("开始打包应用程序...")
        success = build_exe()
        
        if not success:
            print("\n如果遇到问题，请尝试:")
            print("1. 确保已安装所有依赖: pip install -r requirements.txt")
            print("2. 确保PyInstaller已安装: pip install pyinstaller")
            print("3. 运行清理命令: python build_exe.py clean")
            sys.exit(1)