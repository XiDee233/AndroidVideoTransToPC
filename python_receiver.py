#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android USB 视频流接收器
通过ADB端口转发接收Android应用发送的视频帧并显示

使用方法:
1. 确保ADB已安装并在PATH中
2. 连接Android设备并启用USB调试
3. 运行此脚本
4. 在Android应用中开始视频传输
"""

import cv2
import numpy as np
from flask import Flask, request, jsonify
import time
import threading
import logging
import sys
import os
import subprocess
from datetime import datetime
import signal
import queue

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AndroidVideoReceiver:
    def __init__(self, port=9000, gui_mode=False):
        self.port = port
        self.gui_mode = gui_mode  # 新增GUI模式标志
        self.app = Flask(__name__)
        self.latest_frame = None
        self.frame_queue = queue.Queue(maxsize=500)  
        self.frame_count = 0
        self.processed_frame_count = 0
        self.dropped_frame_count = 0
        self.start_time = time.time()
        self.is_receiving = False
        self.last_frame_time = None
        self.last_ping_time = None
        self.connection_count = 0
        self.adb_path = None
        self.server_running = True
        
        # 设置路由
        self.setup_routes()
        
        # 禁用Flask日志输出
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
    
    def setup_routes(self):
        """设置Flask路由"""
        
        @self.app.route('/ping', methods=['GET'])
        def ping():
            self.last_ping_time = time.time()
            return jsonify({"status": "ok", "message": "Python receiver is running"})
        
        @self.app.route('/upload_frame', methods=['POST'])
        def upload_frame():
            try:
                # 第一次连接时检查端口转发状态
                if self.frame_count == 0:
                    print("\n📱 检测到Android应用连接！")
                    if hasattr(self, 'adb_path') and self.adb_path and self.adb_path != 'skip':
                        print("✅ USB模式已激活（反向端口转发已设置）")
                    else:
                        print("💡 WiFi模式连接")
                
                # 获取图像数据
                image_data = request.get_data()
                
                if not image_data:
                    return jsonify({"error": "No image data received"}), 400
                
                # 将字节数据转换为numpy数组
                nparr = np.frombuffer(image_data, np.uint8)
                
                # 解码JPEG图像
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is None:
                    return jsonify({"error": "Failed to decode image"}), 400
                
                # 获取时间戳
                timestamp = request.headers.get('Frame-Timestamp', str(int(time.time() * 1000)))
                
                # 如果是新的连接（之前没有接收），增加连接计数
                if not self.is_receiving:
                    self.connection_count += 1
                    logger.info(f"新连接建立，连接次数: {self.connection_count}")
                
                # 将帧添加到队列中，确保不丢帧
                try:
                    # 非阻塞方式添加到队列
                    self.frame_queue.put_nowait((frame, timestamp))
                    self.latest_frame = frame  # 保留最新帧用于状态显示
                except queue.Full:
                    # 队列满时，丢弃最旧的帧，添加新帧
                    try:
                        self.frame_queue.get_nowait()  # 移除最旧的帧
                        self.frame_queue.put_nowait((frame, timestamp))
                        self.dropped_frame_count += 1
                        logger.warning(f"队列已满，丢弃旧帧。已丢弃帧数: {self.dropped_frame_count}")
                    except queue.Empty:
                        pass
                
                self.frame_count += 1
                self.is_receiving = True
                self.last_frame_time = time.time()
                
                # 第一帧时显示连接成功信息
                if self.frame_count == 1:
                    print(f"\n🎉 视频流连接成功！开始接收视频帧...")
                
                logger.debug(f"接收到帧 #{self.frame_count}, 大小: {frame.shape}, 时间戳: {timestamp}")
                
                return jsonify({
                    "status": "success", 
                    "frame_count": self.frame_count,
                    "timestamp": timestamp
                })
                
            except Exception as e:
                logger.error(f"处理帧时出错: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/status', methods=['GET'])
        def status():
            elapsed_time = time.time() - self.start_time
            fps = self.frame_count / elapsed_time if elapsed_time > 0 else 0
            
            return jsonify({
                "frame_count": self.frame_count,
                "elapsed_time": elapsed_time,
                "fps": fps,
                "is_receiving": self.is_receiving,
                "latest_frame_shape": list(self.latest_frame.shape) if self.latest_frame is not None else None
            })
            
        @self.app.route('/shutdown', methods=['GET'])
        def shutdown():
            """关闭服务器的路由"""
            self.server_running = False
            # 设置关闭标志，让服务器自然退出
            return jsonify({"message": "Server shutdown initiated"})
    
    def find_adb_executable(self):
        """查找ADB可执行文件"""
        # 常见的ADB路径
        possible_paths = [
            'adb',  # 系统PATH中
            'adb.exe',  # Windows
            os.path.expanduser('~/AppData/Local/Android/Sdk/platform-tools/adb.exe'),  # Android Studio默认路径
            'C:/Users/%s/AppData/Local/Android/Sdk/platform-tools/adb.exe' % os.getenv('USERNAME', ''),
            'C:/Android/platform-tools/adb.exe',
            './platform-tools/adb.exe',  # 当前目录
        ]
        
        for path in possible_paths:
            try:
                if path.startswith('C:/Users/') and '%s' in path:
                    continue
                result = subprocess.run([path, 'version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    logger.info(f"✅ 找到ADB: {path}")
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        return None
    
    def download_adb_if_needed(self):
        """如果需要，下载ADB工具"""
        print("\n🔍 正在查找ADB工具...")
        
        adb_path = self.find_adb_executable()
        if adb_path:
            return adb_path
        
        print("\n❌ 未找到ADB工具")
        
        # GUI模式下自动下载ADB
        if self.gui_mode:
            print("\n📥 GUI模式：自动下载ADB工具...")
            return self.auto_download_adb()
        
        # 命令行模式下提供选择
        print("\n📥 ADB安装选项:")
        print("1. 自动下载ADB工具 (推荐)")
        print("2. 手动安装Android SDK")
        print("3. 跳过ADB设置 (仅WiFi模式)")
        
        choice = input("\n请选择 (1/2/3): ").strip()
        
        if choice == '1':
            return self.auto_download_adb()
        elif choice == '2':
            print("\n📋 手动安装步骤:")
            print("1. 下载Android SDK Platform Tools:")
            print("   https://developer.android.com/studio/releases/platform-tools")
            print("2. 解压到任意目录")
            print("3. 将platform-tools目录添加到系统PATH")
            print("4. 重新运行此程序")
            input("\n按Enter键退出...")
            return None
        elif choice == '3':
            print("\n⚠️  跳过ADB设置，仅支持WiFi模式")
            print("请确保Android设备和电脑在同一WiFi网络中")
            return 'skip'
        else:
            print("无效选择")
            return None
    
    def auto_download_adb(self):
        """自动下载ADB工具"""
        try:
            import urllib.request
            import zipfile
            
            print("\n📥 正在下载ADB工具...")
            
            # 创建platform-tools目录
            tools_dir = os.path.join(os.getcwd(), 'platform-tools')
            os.makedirs(tools_dir, exist_ok=True)
            
            # Windows ADB下载链接
            adb_url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
            zip_path = os.path.join(os.getcwd(), 'platform-tools.zip')
            
            # 下载文件
            urllib.request.urlretrieve(adb_url, zip_path)
            
            # 解压文件
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(os.getcwd())
            
            # 删除zip文件
            os.remove(zip_path)
            
            adb_path = os.path.join(tools_dir, 'adb.exe')
            if os.path.exists(adb_path):
                print(f"✅ ADB下载成功: {adb_path}")
                return adb_path
            else:
                print("❌ ADB下载失败")
                return None
                
        except Exception as e:
            print(f"❌ 下载ADB失败: {e}")
            print("请手动安装Android SDK Platform Tools")
            return None
    
    def setup_adb_port_forwarding(self):
        """设置ADB端口转发"""
        try:
            # 查找或下载ADB
            adb_path = self.download_adb_if_needed()
            if not adb_path:
                return False
            elif adb_path == 'skip':
                print("\n⚠️  已跳过ADB设置，使用WiFi模式")
                print("请确保:")
                print("1. Android设备和电脑在同一WiFi网络")
                print("2. 在Android应用中输入电脑的IP地址")
                return True  # 跳过ADB，但继续运行
            
            self.adb_path = adb_path
            print(f"✅ ADB工具已准备: {adb_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ ADB设置失败: {e}")
            print(f"\n❌ ADB设置失败: {e}")
            return False
    
    def setup_reverse_port_forwarding(self):
        """设置反向端口转发（自动执行）"""
        if not hasattr(self, 'adb_path') or not self.adb_path or self.adb_path == 'skip':
            print("\n💡 WiFi模式: 请确保Android设备和电脑在同一网络")
            return True  # WiFi模式或ADB不可用
        
        try:
            # 检查设备连接
            result = subprocess.run([self.adb_path, 'devices'], capture_output=True, text=True)
            devices = [line for line in result.stdout.split('\n')[1:] if line.strip() and '\tdevice' in line]
            
            if not devices:
                print("\n⚠️  未检测到USB连接的Android设备")
                print("请确保:")
                print("1. USB数据线已正常连接")
                print("2. Android设备已启用USB调试")
                print("3. 已授权此电脑进行USB调试")
                print("\n💡 提示: 你也可以使用WiFi模式连接")
                return False
            
            logger.info(f"✅ 检测到 {len(devices)} 个设备: {[d.split()[0] for d in devices]}")
            print(f"✅ 检测到 {len(devices)} 个USB设备")
            
            # 清除现有的反向端口转发
            subprocess.run([self.adb_path, 'reverse', '--remove', 'tcp:9001'], capture_output=True)
            subprocess.run([self.adb_path, 'reverse', '--remove-all'], capture_output=True)
            
            # 设置反向端口转发: 设备的9001端口 -> 主机的9000端口
            # 这样Android应用连接localhost:9001时，会被转发到主机的9000端口
            print(f"🔗 设置反向端口转发: device:9001 -> host:{self.port}")
            result = subprocess.run([
                self.adb_path, 'reverse', 
                'tcp:9001',  # Android设备上的端口
                f'tcp:{self.port}'  # 主机上的端口(9000)
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ 反向端口转发设置失败: {result.stderr}")
                return False
            
            logger.info(f"✅ 反向端口转发已设置: device:9001 -> host:{self.port}")
            print("✅ 反向端口转发设置成功")
            print("\n📱 端口转发说明:")
            print("• Android应用连接 localhost:9001")
            print(f"• 自动转发到主机的 {self.port} 端口")
            print("• 无需手动执行ADB命令")
            return True
            
        except Exception as e:
            logger.error(f"❌ 反向端口转发设置失败: {e}")
            print(f"❌ 反向端口转发设置失败: {e}")
            return False
    
    def display_video_stream(self):
        """显示视频流 - 从队列中逐一处理每一帧"""
        logger.info("开始视频显示线程...")
        
        # 创建窗口
        cv2.namedWindow('Android USB Camera Stream', cv2.WINDOW_AUTOSIZE)
        
        last_frame_time = time.time()
        display_fps = 0
        fps_counter = 0
        fps_start_time = time.time()
        
        try:
            while True:
                try:
                    # 从队列中获取帧，设置超时避免阻塞
                    frame_data = self.frame_queue.get(timeout=0.1)
                    frame, timestamp = frame_data
                    self.processed_frame_count += 1
                    
                    # 计算显示FPS
                    current_time = time.time()
                    if current_time - last_frame_time > 0:
                        fps_counter += 1
                        if fps_counter >= 10:  # 每10帧计算一次FPS
                            display_fps = fps_counter / (current_time - fps_start_time)
                            fps_counter = 0
                            fps_start_time = current_time
                    
                    last_frame_time = current_time
                    
                    # 标记队列任务完成
                    self.frame_queue.task_done()
                    
                except queue.Empty:
                    # 队列为空时显示等待画面
                    waiting_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(waiting_frame, "Waiting for Android camera...", 
                               (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                    cv2.putText(waiting_frame, "Make sure:", 
                               (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
                    cv2.putText(waiting_frame, "1. Android app is running", 
                               (50, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    cv2.putText(waiting_frame, "2. USB debugging is enabled", 
                               (50, 335), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    cv2.putText(waiting_frame, "3. ADB port forwarding is set", 
                               (50, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    
                    cv2.imshow('Android USB Camera Stream', waiting_frame)
                    
                    # 处理按键
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                    
                    continue
                
                # 处理从队列获取到的帧
                if frame is not None:
                     # 添加信息文本
                     height, width = frame.shape[:2]
                     
                     # 背景矩形
                     cv2.rectangle(frame, (10, 10), (450, 140), (0, 0, 0), -1)
                     cv2.rectangle(frame, (10, 10), (450, 140), (0, 255, 0), 2)
                     
                     # 文本信息
                     cv2.putText(frame, f"Android USB Camera Stream", 
                                (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                     cv2.putText(frame, f"Received: {self.frame_count}", 
                                (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                     cv2.putText(frame, f"Processed: {self.processed_frame_count}", 
                                (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                     cv2.putText(frame, f"Dropped: {self.dropped_frame_count}", 
                                (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                     cv2.putText(frame, f"Queue: {self.frame_queue.qsize()}", 
                                (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                     cv2.putText(frame, f"FPS: {display_fps:.1f} | Size: {width}x{height}", 
                                (250, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                     
                     # 底部控制提示
                     cv2.putText(frame, "Press 'q' to quit, 's' to save screenshot", 
                                (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
                     
                     # 显示帧
                     cv2.imshow('Android USB Camera Stream', frame)
                     
                     # 重置接收状态（如果长时间没有新帧）
                     if current_time - last_frame_time > 5:
                         self.is_receiving = False
                
                # 处理按键
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s') and self.latest_frame is not None:
                    # 保存截图
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{timestamp}.jpg"
                    cv2.imwrite(filename, self.latest_frame)
                    logger.info(f"截图已保存: {filename}")
                
                time.sleep(0.01)  # 减少CPU使用
                
        except KeyboardInterrupt:
            logger.info("用户中断显示")
        finally:
            cv2.destroyAllWindows()
    
    def status_monitor(self):
        """状态监控线程 - 定期输出服务器状态"""
        logger.info("状态监控线程已启动")
        
        while True:
            try:
                current_time = time.time()
                uptime = current_time - self.start_time
                
                # 计算运行时间
                hours = int(uptime // 3600)
                minutes = int((uptime % 3600) // 60)
                seconds = int(uptime % 60)
                
                # 检查连接状态
                last_frame_ago = "从未" if self.last_frame_time is None else f"{current_time - self.last_frame_time:.1f}秒前"
                last_ping_ago = "从未" if self.last_ping_time is None else f"{current_time - self.last_ping_time:.1f}秒前"
                
                # 计算处理效率
                processing_rate = (self.processed_frame_count / self.frame_count * 100) if self.frame_count > 0 else 0
                
                # 输出状态信息
                status_msg = f"""📊 服务器状态报告 [{datetime.now().strftime('%H:%M:%S')}]
├─ 运行时间: {hours:02d}:{minutes:02d}:{seconds:02d}
├─ 监听端口: {self.port}
├─ 接收状态: {'🟢 正在接收' if self.is_receiving else '🔴 等待连接'}
├─ 接收帧数: {self.frame_count}
├─ 处理帧数: {self.processed_frame_count}
├─ 丢弃帧数: {self.dropped_frame_count}
├─ 队列大小: {self.frame_queue.qsize()}/100
├─ 处理效率: {processing_rate:.1f}%
├─ 连接次数: {self.connection_count}
├─ 最后帧: {last_frame_ago}
└─ 最后ping: {last_ping_ago}"""
                
                print(status_msg)
                logger.info(f"状态: 运行{hours:02d}:{minutes:02d}:{seconds:02d}, 接收:{self.frame_count}, 处理:{self.processed_frame_count}, 丢弃:{self.dropped_frame_count}, 队列:{self.frame_queue.qsize()}")
                
                # 每10秒输出一次状态
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"状态监控错误: {e}")
                time.sleep(10)
    
    def start_server(self):
        """启动Flask服务器"""
        logger.info(f"启动Flask服务器，端口: {self.port}")
        
        # 检查端口是否可用
        if not self._is_port_available():
            logger.warning(f"端口 {self.port} 被占用，尝试释放...")
            self._force_release_port()
            time.sleep(1)  # 等待端口释放
            
        # 重置服务器状态
        self.server_running = True
        self.frame_count = 0
        self.processed_frame_count = 0
        self.dropped_frame_count = 0
        # 清空队列
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        self.start_time = time.time()
        self.is_receiving = False
        self.latest_frame = None
        
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        
    def _is_port_available(self):
        """检查端口是否可用"""
        try:
            import socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_socket.bind(('localhost', self.port))
            test_socket.close()
            return True
        except Exception:
            return False
            
    def _force_release_port(self):
        """强制释放端口"""
        try:
            # 在Windows上使用netstat和taskkill来释放端口
            import subprocess
            result = subprocess.run(
                ['netstat', '-ano', '|', 'findstr', f':{self.port}'],
                shell=True, capture_output=True, text=True
            )
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'LISTENING' in line:
                        parts = line.split()
                        if len(parts) > 4:
                            pid = parts[-1]
                            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                            logger.info(f"已终止占用端口 {self.port} 的进程 PID: {pid}")
        except Exception as e:
            logger.warning(f"强制释放端口失败: {e}")
        
    def _run_server(self):
        """在线程中运行Flask服务器"""
        try:
            # 配置Flask服务器选项，允许端口重用
            import socket
            from werkzeug.serving import WSGIRequestHandler, make_server
            
            class ReusePortWSGIRequestHandler(WSGIRequestHandler):
                def setup(self):
                    super().setup()
                    self.request.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 使用make_server创建服务器实例，便于控制
            self.server_instance = make_server(
                '0.0.0.0', 
                self.port, 
                self.app,
                request_handler=ReusePortWSGIRequestHandler
            )
            
            # 设置超时，让服务器能够响应停止信号
            self.server_instance.timeout = 0.5
            
            logger.info(f"Flask服务器启动，监听端口: {self.port}")
            
            # 使用serve_forever，但在单独线程中检查停止标志
            while self.server_running:
                try:
                    self.server_instance.handle_request()
                except OSError:
                    # 服务器已关闭，正常退出
                    break
                except Exception as e:
                    if self.server_running:
                        logger.error(f"处理请求时出错: {e}")
                    break
                
            logger.info("Flask服务器收到停止信号，正在关闭...")
            
        except Exception as e:
            if self.server_running:
                logger.error(f"Flask服务器运行错误: {e}")
            else:
                logger.info("Flask服务器已正常关闭")
        finally:
            if hasattr(self, 'server_instance'):
                try:
                    self.server_instance.server_close()
                    logger.info("服务器socket已关闭")
                except Exception as e:
                    logger.warning(f"关闭服务器socket时出错: {e}")
        
    def stop_server(self):
        """停止Flask服务器"""
        logger.info("正在停止Flask服务器...")
        try:
            # 设置停止标志
            self.server_running = False
            
            # 清理反向端口转发
            if hasattr(self, 'adb_path') and self.adb_path and self.adb_path != 'skip':
                try:
                    subprocess.run([self.adb_path, 'reverse', '--remove', 'tcp:9001'], capture_output=True, timeout=2)
                    subprocess.run([self.adb_path, 'reverse', '--remove-all'], capture_output=True, timeout=2)
                    logger.info("反向端口转发已清理")
                except subprocess.TimeoutExpired:
                    logger.warning("清理端口转发超时")
                except Exception as e:
                    logger.warning(f"清理端口转发失败: {e}")
            
            # 关闭服务器实例
            if hasattr(self, 'server_instance'):
                try:
                    # 直接关闭socket，不使用shutdown()避免阻塞
                    self.server_instance.server_close()
                    logger.info("Flask服务器实例已关闭")
                except Exception as e:
                    logger.warning(f"关闭服务器实例时出错: {e}")
                
            # 等待服务器线程结束，但设置较短的超时时间
            if hasattr(self, 'server_thread') and self.server_thread.is_alive():
                self.server_thread.join(timeout=1.0)  # 减少到1秒
                if self.server_thread.is_alive():
                    logger.warning("服务器线程未能在超时时间内结束，强制设置为daemon")
                    # 将线程设置为daemon，这样主程序退出时会强制结束
                    self.server_thread.daemon = True
                else:
                    logger.info("服务器线程已结束")
                
            logger.info("Flask服务器已完全停止")
                
        except Exception as e:
            logger.error(f"停止服务器时出错: {e}")
    
    def run(self):
        """运行接收器"""
        print("=== Android USB 视频流接收器 ===")
        print("此程序接收Android应用通过USB传输的视频流")
        print()
        
        # 准备ADB工具（不强制要求设备连接）
        adb_ready = self.setup_adb_port_forwarding()
        
        # 自动设置反向端口转发
        if adb_ready:
            port_forward_success = self.setup_reverse_port_forwarding()
        else:
            port_forward_success = False
        
        print(f"\n✅ 服务器准备就绪，监听端口: {self.port}")
        print("\n📱 使用说明:")
        print("1. 先保持此程序运行")
        if adb_ready and hasattr(self, 'adb_path') and self.adb_path != 'skip':
            if port_forward_success:
                print("2. 连接Android设备到电脑（USB数据线）")
                print("3. 在Android设备上启动VideoTrans应用")
                print("4. 点击'开始传输'按钮（端口转发已自动设置）")
                print("\n💡 支持模式: USB连接（自动端口转发）+ WiFi连接")
            else:
                print("2. 连接Android设备到电脑（USB数据线）")
                print("3. 手动执行: adb reverse tcp:9001 tcp:9000")
                print("4. 在Android设备上启动VideoTrans应用")
                print("5. 点击'开始传输'按钮")
                print("\n💡 支持模式: USB连接 + WiFi连接")
        else:
            print("2. 确保Android设备和电脑在同一WiFi网络")
            print("3. 在Android设备上启动VideoTrans应用")
            print("4. 输入电脑IP地址并点击'开始传输'")
            print("\n💡 当前模式: 仅WiFi连接")
        print("5. 视频流将显示在OpenCV窗口中")
        print("6. 按'q'键退出，按's'键截图")
        print("\n⏳ 等待Android应用连接...\n")
        
        # 启动显示线程
        display_thread = threading.Thread(target=self.display_video_stream, daemon=True)
        display_thread.start()
        
        # 启动状态监控线程
        status_thread = threading.Thread(target=self.status_monitor, daemon=True)
        status_thread.start()
        
        try:
            # 启动Flask服务器
            self.start_server()
            
            # 等待服务器线程运行，保持主线程活跃
            logger.info("服务器已启动，主线程等待...")
            while self.server_running:
                try:
                    # 检查服务器线程是否还在运行
                    if hasattr(self, 'server_thread') and not self.server_thread.is_alive():
                        logger.warning("服务器线程意外退出")
                        break
                    time.sleep(1)  # 每秒检查一次
                except KeyboardInterrupt:
                    logger.info("\n接收到中断信号，正在停止服务器...")
                    self.stop_server()
                    break
                    
        except KeyboardInterrupt:
            logger.info("\n程序被用户中断")
            self.stop_server()
        except Exception as e:
            logger.error(f"服务器错误: {e}")
            self.stop_server()
        finally:
            # 清理反向端口转发
            try:
                if hasattr(self, 'adb_path') and self.adb_path and self.adb_path != 'skip':
                    subprocess.run([self.adb_path, 'reverse', '--remove', 'tcp:9001'], capture_output=True)
                    subprocess.run([self.adb_path, 'reverse', '--remove-all'], capture_output=True)
                    logger.info("反向端口转发已清理")
            except:
                pass
            
            print("\n程序结束")

def main():
    # 检查依赖
    try:
        import cv2
        import flask
        import numpy
    except ImportError as e:
        print(f"❌ 缺少必要的Python库: {e}")
        print("\n请安装依赖:")
        print("pip install opencv-python flask numpy")
        input("\n按Enter键退出...")
        return
    
    # 获取端口设置
    port = 9000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("无效的端口号，使用默认端口9000")
    
    # 启动接收器
    receiver = AndroidVideoReceiver(port)
    receiver.run()

if __name__ == "__main__":
    main()