#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB连接诊断工具
帮助诊断Android设备USB连接问题
"""

import subprocess
import os
import sys
import time

def check_adb_installation():
    """检查ADB安装状态"""
    print("🔍 检查ADB安装状态...")
    
    # 常见的ADB路径
    possible_paths = [
        'adb',
        'adb.exe',
        os.path.expanduser('~/AppData/Local/Android/Sdk/platform-tools/adb.exe'),
        './platform-tools/adb.exe',
    ]
    
    for path in possible_paths:
        try:
            result = subprocess.run([path, 'version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ 找到ADB: {path}")
                print(f"   版本信息: {result.stdout.strip().split()[4]}")
                return path
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
    
    print("❌ 未找到ADB工具")
    return None

def check_device_connection(adb_path):
    """检查设备连接状态"""
    print("\n📱 检查设备连接状态...")
    
    try:
        result = subprocess.run([adb_path, 'devices', '-l'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        
        print(f"ADB输出:")
        for line in lines:
            print(f"  {line}")
        
        # 分析设备状态
        devices = []
        for line in lines[1:]:  # 跳过标题行
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]
                    devices.append((device_id, status))
        
        if not devices:
            print("❌ 未检测到任何设备")
            return False
        
        print(f"\n检测到 {len(devices)} 个设备:")
        for device_id, status in devices:
            if status == 'device':
                print(f"✅ {device_id}: 已连接并授权")
            elif status == 'unauthorized':
                print(f"⚠️  {device_id}: 未授权 - 请在手机上允许USB调试")
            elif status == 'offline':
                print(f"⚠️  {device_id}: 离线状态")
            else:
                print(f"❓ {device_id}: {status}")
        
        # 检查是否有可用设备
        authorized_devices = [d for d in devices if d[1] == 'device']
        return len(authorized_devices) > 0
        
    except Exception as e:
        print(f"❌ 检查设备时出错: {e}")
        return False

def test_port_forwarding(adb_path, port=8081):
    """测试端口转发"""
    print(f"\n🔗 测试端口转发 (端口 {port})...")
    
    try:
        # 清除现有转发
        subprocess.run([adb_path, 'forward', '--remove', f'tcp:{port}'], capture_output=True)
        
        # 设置端口转发
        result = subprocess.run([
            adb_path, 'forward', 
            f'tcp:{port}', 
            f'tcp:{port}'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 端口转发设置成功: localhost:{port} -> device:{port}")
            
            # 列出当前转发
            list_result = subprocess.run([adb_path, 'forward', '--list'], capture_output=True, text=True)
            if list_result.returncode == 0 and list_result.stdout.strip():
                print("当前端口转发列表:")
                for line in list_result.stdout.strip().split('\n'):
                    print(f"  {line}")
            
            return True
        else:
            print(f"❌ 端口转发设置失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 端口转发测试失败: {e}")
        return False

def check_usb_drivers():
    """检查USB驱动状态"""
    print("\n🔧 检查USB驱动状态...")
    
    try:
        # 在Windows上检查设备管理器
        if os.name == 'nt':
            result = subprocess.run(['powershell', '-Command', 
                'Get-PnpDevice | Where-Object {$_.FriendlyName -like "*Android*" -or $_.FriendlyName -like "*ADB*"} | Select-Object FriendlyName, Status'], 
                capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                print("检测到的Android相关设备:")
                lines = result.stdout.strip().split('\n')
                for line in lines[2:]:  # 跳过标题行
                    if line.strip():
                        print(f"  {line.strip()}")
            else:
                print("未检测到Android设备或驱动")
        else:
            print("非Windows系统，跳过驱动检查")
            
    except Exception as e:
        print(f"⚠️  驱动检查失败: {e}")

def provide_troubleshooting_tips():
    """提供故障排除建议"""
    print("\n🛠️  故障排除建议:")
    print("\n1. 基础检查:")
    print("   • 确保使用数据线而非充电线")
    print("   • 尝试不同的USB端口")
    print("   • 重新插拔USB线")
    
    print("\n2. Android设备设置:")
    print("   • 设置 → 开发者选项 → USB调试 (开启)")
    print("   • 设置 → 开发者选项 → USB配置 → 选择'文件传输'或'PTP'")
    print("   • 设置 → 开发者选项 → 撤销USB调试授权 (然后重新授权)")
    
    print("\n3. 电脑端检查:")
    print("   • 安装手机厂商的USB驱动程序")
    print("   • 重启ADB服务: adb kill-server && adb start-server")
    print("   • 以管理员身份运行命令提示符")
    
    print("\n4. 常见品牌驱动下载:")
    print("   • 小米: https://www.mi.com/service/bijiben/drivers/")
    print("   • 华为: https://consumer.huawei.com/cn/support/hisuite/")
    print("   • OPPO: https://www.oppo.cn/service/mobile/")
    print("   • vivo: https://www.vivo.com.cn/service/")
    print("   • 三星: https://www.samsung.com/cn/support/mobile-devices/")

def main():
    print("=== Android USB连接诊断工具 ===")
    print("此工具帮助诊断Android设备USB连接问题\n")
    
    # 1. 检查ADB
    adb_path = check_adb_installation()
    if not adb_path:
        print("\n❌ 请先安装ADB工具")
        print("可以运行 python_receiver.py 自动下载ADB")
        input("\n按Enter键退出...")
        return
    
    # 2. 检查设备连接
    device_connected = check_device_connection(adb_path)
    
    # 3. 如果有设备，测试端口转发
    if device_connected:
        test_port_forwarding(adb_path)
    
    # 4. 检查USB驱动
    check_usb_drivers()
    
    # 5. 提供故障排除建议
    provide_troubleshooting_tips()
    
    print("\n" + "="*50)
    if device_connected:
        print("✅ 诊断完成！设备连接正常，可以使用USB模式")
    else:
        print("❌ 设备连接有问题，请按照上述建议进行故障排除")
        print("或者可以使用WiFi模式作为替代方案")
    
    input("\n按Enter键退出...")

if __name__ == '__main__':
    main()