#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型量化脚本
将YOLO模型量化以减少模型大小和提高推理速度
"""

import torch
from ultralytics import YOLO
import os

def quantize_yolo_model(model_path, output_path=None, format='onnx'):
    """
    量化YOLO模型
    
    Args:
        model_path (str): 原始模型路径
        output_path (str): 输出路径，如果为None则自动生成
        format (str): 导出格式 ('onnx', 'torchscript', 'tflite')
    """
    print(f"正在加载模型: {model_path}")
    
    # 加载YOLO模型
    model = YOLO(model_path)
    
    # 如果没有指定输出路径，自动生成
    if output_path is None:
        base_name = os.path.splitext(model_path)[0]
        if format == 'onnx':
            output_path = f"{base_name}_quantized.onnx"
        elif format == 'torchscript':
            output_path = f"{base_name}_quantized.torchscript"
        elif format == 'tflite':
            output_path = f"{base_name}_quantized.tflite"
        else:
            output_path = f"{base_name}_quantized.pt"
    
    print(f"开始量化模型...")
    
    try:
        if format == 'onnx':
            # 导出为ONNX格式（支持量化）
            model.export(
                format='onnx',
                dynamic=True,
                simplify=True,
                opset=11,
                int8=True  # 启用INT8量化
            )
            print(f"ONNX量化模型已保存")
            
        elif format == 'tflite':
            # 导出为TensorFlow Lite格式（支持量化）
            model.export(
                format='tflite',
                int8=True  # 启用INT8量化
            )
            print(f"TensorFlow Lite量化模型已保存")
            
        elif format == 'torchscript':
            # 使用PyTorch量化
            # 首先导出为TorchScript
            model.export(format='torchscript')
            
            # 加载TorchScript模型进行量化
            base_name = os.path.splitext(model_path)[0]
            ts_path = f"{base_name}.torchscript"
            
            if os.path.exists(ts_path):
                # 加载TorchScript模型
                ts_model = torch.jit.load(ts_path)
                ts_model.eval()
                
                # 应用动态量化
                quantized_model = torch.quantization.quantize_dynamic(
                    ts_model,
                    {torch.nn.Linear, torch.nn.Conv2d},
                    dtype=torch.qint8
                )
                
                # 保存量化模型
                torch.jit.save(quantized_model, output_path)
                print(f"TorchScript量化模型已保存到: {output_path}")
                
                # 清理临时文件
                os.remove(ts_path)
            else:
                print("TorchScript导出失败")
                
        else:
            # 使用PyTorch原生量化（针对.pt文件）
            print("使用PyTorch原生量化...")
            
            # 获取模型的PyTorch版本
            pytorch_model = model.model
            pytorch_model.eval()
            
            # 应用动态量化
            quantized_model = torch.quantization.quantize_dynamic(
                pytorch_model,
                {torch.nn.Linear, torch.nn.Conv2d, torch.nn.ConvTranspose2d},
                dtype=torch.qint8
            )
            
            # 保存量化模型
            torch.save({
                'model': quantized_model,
                'quantized': True,
                'original_model_path': model_path
            }, output_path)
            
            print(f"PyTorch量化模型已保存到: {output_path}")
            
    except Exception as e:
        print(f"量化过程中出现错误: {e}")
        return False
    
    return True

def compare_model_sizes(original_path, quantized_path):
    """
    比较原始模型和量化模型的大小
    """
    if os.path.exists(original_path) and os.path.exists(quantized_path):
        original_size = os.path.getsize(original_path) / (1024 * 1024)  # MB
        quantized_size = os.path.getsize(quantized_path) / (1024 * 1024)  # MB
        compression_ratio = (original_size - quantized_size) / original_size * 100
        
        print(f"\n模型大小比较:")
        print(f"原始模型: {original_size:.2f} MB")
        print(f"量化模型: {quantized_size:.2f} MB")
        print(f"压缩率: {compression_ratio:.1f}%")
        
        return compression_ratio
    return 0

def main():
    # 模型路径
    model_path = "d:/AndroidStudioProjects/VideoTrans/best.pt"
    
    if not os.path.exists(model_path):
        print(f"错误: 找不到模型文件 {model_path}")
        return
    
    print("YOLO模型量化工具")
    print("=" * 50)
    
    # 显示可用的量化选项
    print("可用的量化格式:")
    print("1. ONNX (推荐，支持多平台)")
    print("2. TensorFlow Lite (移动端优化)")
    print("3. TorchScript (PyTorch生态)")
    print("4. PyTorch原生量化")
    
    # 用户选择
    choice = input("\n请选择量化格式 (1-4): ").strip()
    
    format_map = {
        '1': 'onnx',
        '2': 'tflite', 
        '3': 'torchscript',
        '4': 'pytorch'
    }
    
    selected_format = format_map.get(choice, 'onnx')
    
    print(f"\n选择的格式: {selected_format}")
    print("开始量化...")
    
    # 执行量化
    success = quantize_yolo_model(model_path, format=selected_format)
    
    if success:
        print("\n量化完成！")
        
        # 尝试比较文件大小（仅对某些格式有效）
        if selected_format in ['pytorch', 'torchscript']:
            base_name = os.path.splitext(model_path)[0]
            if selected_format == 'pytorch':
                quantized_path = f"{base_name}_quantized.pt"
            else:
                quantized_path = f"{base_name}_quantized.torchscript"
            
            compare_model_sizes(model_path, quantized_path)
    else:
        print("\n量化失败！")

if __name__ == "__main__":
    main()