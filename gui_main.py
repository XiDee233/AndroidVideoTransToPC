# 在文件顶部导入日志模块
import sys
import os
import cv2
import numpy as np
import logging  # 添加日志模块
import queue  # 添加队列模块
import threading  # 添加线程模块
from ultralytics import YOLO
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QComboBox, QGroupBox, QSlider)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QObject, QMutex, QWaitCondition, QMutexLocker
from PyQt5.QtGui import QImage, QPixmap
from tracker import ObjectTracker
from python_receiver import AndroidVideoReceiver
import random
import threading
import time


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，支持开发环境和打包后的环境"""
    try:
        # PyInstaller创建临时文件夹，并将路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    except Exception:
        # 开发环境中使用当前目录
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("detection_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("YOLODetection")


class DetectionWorker(QObject):
    finished = pyqtSignal()
    image_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.source_type = None
        self.file_path = None
        self.running = True
        self.restart = False
        self.abort = False
        self.currently_processing = False
        self.tracker = ObjectTracker(max_lost=4)
        self.id_colors = {}
        self.show_inactive = True
        self.paused = False
        
        # 生产者-消费者队列
        self.detection_queue = queue.Queue(maxsize=10)  # 检测结果队列
        self.tracking_thread = None  # 跟踪线程
        self.tracking_running = False  # 跟踪线程运行状态
        
        # USB手机相关属性
        self.usb_receiver = None
        self.usb_server_thread = None
        self.usb_server_running = False
        self.usb_connected_status_shown = False  # 标记是否已显示连接状态
        
        # 计数线相关属性
        self.counting_line = None  # 将在第一帧初始化
        self.line_position = 0.5  # 默认在画面中间
        self.line_direction = 'horizontal'  # 水平线
        self.crossed_ids = set()  # 已经穿过线的ID集合
        self.counter = 0  # 计数器
        self.total_ids = set()  # 跟踪所有出现过的ID
        
        # 添加双向计数属性
        self.left_to_right_counter = 0  # 从左到右计数
        self.right_to_left_counter = 0  # 从右到左计数
        self.top_to_bottom_counter = 0  # 从上到下计数
        self.bottom_to_top_counter = 0  # 从下到上计数
        self.crossed_direction = {}  # 记录每个ID穿过的方向

    def set_line_position(self, position):
        """设置计数线位置 (0-1 范围内的相对位置)"""
        with QMutexLocker(self.mutex):
            self.line_position = max(0.0, min(1.0, position))

    def set_line_direction(self, direction):
        """设置计数线方向 ('horizontal' 或 'vertical')"""
        with QMutexLocker(self.mutex):
            # 只有当方向确实改变时才重置计数线
            if self.line_direction != direction:
                self.line_direction = direction
                self.counting_line = None  # 重置计数线，使其在下一帧重新初始化

    # 修改reset_counter方法，重置所有计数器
    def reset_counter(self):
        """重置计数器"""
        with QMutexLocker(self.mutex):
            self.counter = 0
            self.left_to_right_counter = 0
            self.right_to_left_counter = 0
            self.top_to_bottom_counter = 0
            self.bottom_to_top_counter = 0
            self.crossed_ids = set()
            self.crossed_direction = {}
            self.total_ids = set()  # 重置总ID集合

    def set_source(self, source_type, file_path=None):
        with QMutexLocker(self.mutex):
            self.source_type = source_type
            self.file_path = file_path
            self.restart = True
            self.abort = False
            self.condition.wakeOne()
            self.status_changed.emit(f"准备检测: {source_type}")
    
    def start_usb_server(self):
        """启动USB手机视频接收服务器"""
        try:
            self.usb_connected_status_shown = False  # 重置连接状态标志
            
            # 如果服务器正在运行，先停止它
            if self.usb_server_running:
                self.stop_usb_server()
                time.sleep(0.5)  # 等待服务器完全停止
            
            # 总是重新创建AndroidVideoReceiver实例，确保状态干净
            self.usb_receiver = AndroidVideoReceiver(port=9000, gui_mode=True)
            # 设置ADB端口转发
            adb_ready = self.usb_receiver.setup_adb_port_forwarding()
            if adb_ready:
                self.usb_receiver.setup_reverse_port_forwarding()
            
            # 在单独线程中启动Flask服务器
            self.usb_server_thread = threading.Thread(
                target=self.usb_receiver.start_server, 
                daemon=True
            )
            self.usb_server_thread.start()
            self.usb_server_running = True
            self.status_changed.emit("USB服务器已启动，等待手机连接...")
            return True
        except Exception as e:
            self.error_occurred.emit(f"启动USB服务器失败: {str(e)}")
            return False
    
    def stop_usb_server(self):
        """停止USB手机视频接收服务器"""
        try:
            self.usb_server_running = False
            self.usb_connected_status_shown = False  # 重置连接状态标志
            
            if self.usb_receiver:
                # 调用AndroidVideoReceiver的stop_server方法来正确停止Flask服务器
                try:
                    self.usb_receiver.stop_server()
                except Exception as e:
                    logger.warning(f"停止USB接收器时出错: {e}")
                finally:
                    self.usb_receiver = None
            
            # 等待服务器线程结束，但减少等待时间避免卡死
            if hasattr(self, 'usb_server_thread') and self.usb_server_thread and self.usb_server_thread.is_alive():
                self.usb_server_thread.join(timeout=0.5)  # 减少到0.5秒
                if self.usb_server_thread.is_alive():
                    logger.warning("USB服务器线程未能在超时时间内结束")
                
            self.status_changed.emit("USB服务器已停止")
        except Exception as e:
            logger.error(f"停止USB服务器失败: {str(e)}")
            self.error_occurred.emit(f"停止USB服务器失败: {str(e)}")

    def start_tracking_thread(self):
        """启动跟踪消费者线程"""
        if self.tracking_thread is None or not self.tracking_thread.is_alive():
            self.tracking_running = True
            self.tracking_thread = threading.Thread(target=self.tracking_consumer, daemon=True)
            self.tracking_thread.start()
    
    def stop_tracking_thread(self):
        """停止跟踪消费者线程"""
        self.tracking_running = False
        # 清空队列并添加停止信号
        try:
            while not self.detection_queue.empty():
                self.detection_queue.get_nowait()
        except queue.Empty:
            pass
        # 添加停止信号
        try:
            self.detection_queue.put(None, timeout=0.1)
        except queue.Full:
            pass
        
        if self.tracking_thread and self.tracking_thread.is_alive():
             self.tracking_thread.join(timeout=1.0)
    
    def tracking_consumer(self):
        """跟踪消费者线程 - 处理检测结果队列"""
        while self.tracking_running:
            try:
                # 从队列获取检测结果
                queue_data = self.detection_queue.get(timeout=0.1)
                
                # 检查停止信号
                if queue_data is None:
                    break
                
                frame = queue_data['frame']
                detections = queue_data['detections']
                counting_line = queue_data['counting_line']
                line_direction = queue_data['line_direction']
                
                # 更新tracker
                tracks = self.tracker.update(detections, frame_shape=frame.shape)
                
                # 检查是否有物体穿过计数线
                for track in tracks:
                    # 添加ID到总ID集合
                    self.total_ids.add(track['id'])
                    if self.check_line_crossing(track):
                        self.counter += 1
                        
                # 绘制检测框和轨迹（每个id唯一颜色）
                annotated_frame = frame.copy()
                for i, track in enumerate(tracks):
                    # 判断活跃性
                    trk_obj = self.tracker.trackers[i] if i < len(self.tracker.trackers) else None
                    is_active = (trk_obj.lost == 0) if trk_obj else True
                    if self.show_inactive or is_active:
                        x1, y1, x2, y2 = map(int, track['bbox'])
                        color = self.get_color(track['id'])
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated_frame, f"ID:{track['id']}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                # 画轨迹（每个id唯一颜色）
                for i, track in enumerate(tracks):
                    trk_obj = self.tracker.trackers[i] if i < len(self.tracker.trackers) else None
                    is_active = (trk_obj.lost == 0) if trk_obj else True
                    if self.show_inactive or is_active:
                        color = self.get_color(track['id'])
                        trace = track['trace']
                        if len(trace) > 1:
                            for j in range(1, len(trace)):
                                pt1 = (int(trace[j-1][0]), int(trace[j-1][1]))
                                pt2 = (int(trace[j][0]), int(trace[j][1]))
                                cv2.line(annotated_frame, pt1, pt2, color, 2)
                                
                # 绘制计数线（确保计数线已初始化）
                if counting_line is not None:
                    line_color = (0, 0, 255)  # 红色
                    cv2.line(annotated_frame, counting_line[0], counting_line[1], line_color, 2)
                
                # 显示计数和总ID数
                count_text = f"Total Count: {self.counter}"
                cv2.putText(annotated_frame, count_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                
                # 显示当前检测到的总ID数
                total_ids_text = f"Total IDs: {len(self.total_ids)}"
                cv2.putText(annotated_frame, total_ids_text, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                
                # 显示双向计数结果
                if line_direction == 'horizontal':
                    # 显示从上到下和从下到上的计数
                    top_to_bottom_text = f"Top→Bottom: {self.top_to_bottom_counter}"
                    bottom_to_top_text = f"Bottom→Top: {self.bottom_to_top_counter}"
                    cv2.putText(annotated_frame, top_to_bottom_text, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
                    cv2.putText(annotated_frame, bottom_to_top_text, (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
                else:  # vertical
                    # 显示从左到右和从右到左的计数
                    left_to_right_text = f"Left→Right: {self.left_to_right_counter}"
                    right_to_left_text = f"Right→Left: {self.right_to_left_counter}"
                    cv2.putText(annotated_frame, left_to_right_text, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
                    cv2.putText(annotated_frame, right_to_left_text, (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
                
                # 转为RGB并发送
                rgb_image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                self.image_ready.emit(rgb_image)
                
                # 标记任务完成
                self.detection_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.error_occurred.emit(f"跟踪处理错误: {str(e)}")
                break

    def stop(self):
        with QMutexLocker(self.mutex):
            self.abort = True
            self.condition.wakeOne()
            self.status_changed.emit("已停止")
        
        # 停止跟踪线程
        self.stop_tracking_thread()
        
        # 在mutex锁外停止USB服务器，避免死锁
        if self.source_type == "usb_phone" and self.usb_server_running:
            self.stop_usb_server()

    def pause(self):
        with QMutexLocker(self.mutex):
            self.paused = True
            self.status_changed.emit("已暂停")

    def resume(self):
        with QMutexLocker(self.mutex):
            self.paused = False
            self.condition.wakeOne()
            self.status_changed.emit("已恢复")

    def run(self):
        self.status_changed.emit("就绪")
        cap = None
        while self.running:
            with QMutexLocker(self.mutex):
                if self.paused:
                    self.status_changed.emit("已暂停，等待恢复...")
                    self.condition.wait(self.mutex)
                if not self.restart and not self.abort:
                    self.status_changed.emit("等待输入...")
                    self.condition.wait(self.mutex)
                if self.abort:
                    self.abort = False
                    self.restart = False
                    if cap is not None:
                        cap.release()
                        cap = None
                    continue
                if self.restart:
                    if cap is not None:
                        cap.release()
                        cap = None
                self.currently_processing = True
                self.restart = False

            try:
                # 启动跟踪消费者线程
                self.start_tracking_thread()
                
                self.status_changed.emit(f"开始检测: {self.source_type}")
                if self.source_type == "camera":
                    if cap is None:
                        cap = cv2.VideoCapture(0)
                        if not cap.isOpened():
                            error_msg = "无法打开摄像头"
                            logger.error(error_msg)  # 记录到日志
                            self.error_occurred.emit(error_msg)
                            continue
                    while self.currently_processing and self.running:
                        with QMutexLocker(self.mutex):
                            if self.paused:
                                if self.usb_connected_status_shown:
                                    self.status_changed.emit("视频流已暂停，等待恢复...")
                                else:
                                    self.status_changed.emit("已暂停，等待恢复...")
                                self.condition.wait(self.mutex)
                            if self.abort or self.restart:
                                break
                        ret, frame = cap.read()
                        if not ret:
                            self.error_occurred.emit("摄像头读取失败")
                            break
                        self.process_frame(frame)
                elif self.source_type == "video":
                    if not self.file_path:
                        continue
                    if cap is None:
                        cap = cv2.VideoCapture(self.file_path)
                        if not cap.isOpened():
                            error_msg = "无法打开视频文件"
                            logger.error(error_msg)  # 记录到日志
                            self.error_occurred.emit(error_msg)
                            continue
                    while self.currently_processing and self.running:
                        with QMutexLocker(self.mutex):
                            if self.paused:
                                self.status_changed.emit("已暂停，等待恢复...")
                                self.condition.wait(self.mutex)
                            if self.abort or self.restart:
                                break
                        ret, frame = cap.read()
                        if not ret:
                            self.status_changed.emit("视频播放完成")
                            break
                        self.process_frame(frame)
                elif self.source_type == "image":
                    if not self.file_path:
                        continue
                    frame = cv2.imread(self.file_path)
                    if frame is None:
                        self.error_occurred.emit("无法读取图片文件")
                    else:
                        self.process_frame(frame)
                        self.status_changed.emit("图片检测完成")
                elif self.source_type == "usb_phone":
                    # 启动USB服务器
                    if not self.start_usb_server():
                        continue
                    
                    # 等待并处理来自手机的视频帧
                    while self.currently_processing and self.running:
                        with QMutexLocker(self.mutex):
                            if self.paused:
                                if self.usb_connected_status_shown:
                                    self.status_changed.emit("图像识别已暂停，视频流继续接收...")
                                else:
                                    self.status_changed.emit("已暂停，等待恢复...")
                                self.condition.wait(self.mutex)
                            if self.abort or self.restart:
                                break
                        
                        if self.usb_receiver:
                            try:
                                # 从队列中获取帧，设置超时避免阻塞
                                frame_data = self.usb_receiver.frame_queue.get(timeout=0.1)
                                frame, timestamp = frame_data
                                
                                # 只在第一次检测到连接时更新状态
                                if not self.usb_connected_status_shown:
                                    self.status_changed.emit("手机已连接，正在接收视频流...")
                                    self.usb_connected_status_shown = True
                                
                                # 只有在非暂停状态下才处理图像
                                if not self.paused:
                                    self.process_frame(frame)
                                    
                            except queue.Empty:
                                # 队列为空
                                # 重置连接状态标志
                                if self.usb_connected_status_shown:
                                    self.usb_connected_status_shown = False
                                    self.status_changed.emit("USB服务器已启动，等待手机连接...")
                                time.sleep(0.1)
                            except Exception as e:
                                logger.error(f"获取帧数据时出错: {e}")
                                time.sleep(0.1)
                        else:
                            time.sleep(0.1)  # 等待接收器初始化
                    
                    # USB服务器将在stop方法中停止，这里不需要重复调用
                    pass
            except Exception as e:
                error_msg = f"处理错误: {str(e)}"
                logger.exception(error_msg)  # 记录详细的异常信息到日志
                self.error_occurred.emit(error_msg)
            finally:
                self.currently_processing = False
        if cap is not None:
            cap.release()
            cap = None
        self.finished.emit()

    def get_color(self, track_id):
        if track_id not in self.id_colors:
            random.seed(track_id)
            self.id_colors[track_id] = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            )
        return self.id_colors[track_id]

    # 修改check_line_crossing方法，添加方向检测
    def check_line_crossing(self, track):
        """检查轨迹是否穿过计数线，并判断穿过方向"""
        # 如果计数线未初始化，直接返回False
        if self.counting_line is None:
            return False
            
        if track['id'] in self.crossed_ids:
            return False
            
        trace = track['trace']
        if len(trace) < 2:
            return False
            
        # 获取最近的两个点
        p1 = trace[-2]
        p2 = trace[-1]
        
        try:
            if self.line_direction == 'horizontal':
                # 水平线，检查是否从上到下或从下到上穿过
                line_y = self.counting_line[0][1]  # 线的y坐标
                if p1[1] < line_y and p2[1] >= line_y:
                    # 从上到下穿过
                    self.crossed_ids.add(track['id'])
                    self.crossed_direction[track['id']] = 'top_to_bottom'
                    self.top_to_bottom_counter += 1
                    return True
                elif p1[1] >= line_y and p2[1] < line_y:
                    # 从下到上穿过
                    self.crossed_ids.add(track['id'])
                    self.crossed_direction[track['id']] = 'bottom_to_top'
                    self.bottom_to_top_counter += 1
                    return True
            else:  # vertical
                # 垂直线，检查是否从左到右或从右到左穿过
                line_x = self.counting_line[0][0]  # 线的x坐标
                if p1[0] < line_x and p2[0] >= line_x:
                    # 从左到右穿过
                    self.crossed_ids.add(track['id'])
                    self.crossed_direction[track['id']] = 'left_to_right'
                    self.left_to_right_counter += 1
                    return True
                elif p1[0] >= line_x and p2[0] < line_x:
                    # 从右到左穿过
                    self.crossed_ids.add(track['id'])
                    self.crossed_direction[track['id']] = 'right_to_left'
                    self.right_to_left_counter += 1
                    return True
        except Exception as e:
            logger.error(f"计数线检测错误: {str(e)}")  # 记录到日志而不是显示在画面上
            # 不抛出异常，继续执行
                
        return False

    # 修改DetectionWorker类中的方法
    
    def process_frame(self, frame):
        """检测生产者 - 处理单帧图像并将结果放入队列"""
        if self.paused:
            return
            
        try:
            # 初始化或更新计数线位置
            h, w = frame.shape[:2]
            with QMutexLocker(self.mutex):
                if self.line_direction == 'horizontal':
                    y = int(h * self.line_position)
                    self.counting_line = [(0, y), (w, y)]
                else:  # vertical
                    x = int(w * self.line_position)
                    self.counting_line = [(x, 0), (x, h)]
                    
            # 使用YOLO模型进行检测
            results = self.model.predict(frame, conf=0.5, iou=0.7, imgsz=640)
            boxes = results[0].boxes
            dets = []
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    conf = float(box.conf[0]) if hasattr(box, 'conf') else 0
                    if conf < 0.5:
                        continue
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    cls = int(box.cls[0]) if hasattr(box, 'cls') else 0
                    dets.append([x1, y1, x2, y2, conf, cls])
            
            # 将检测结果和帧信息放入队列供跟踪线程处理
            queue_data = {
                'frame': frame.copy(),
                'detections': dets,
                'counting_line': self.counting_line,
                'line_direction': self.line_direction
            }
            
            try:
                self.detection_queue.put(queue_data, timeout=0.01)
            except queue.Full:
                # 队列满时跳过当前帧
                pass
                
        except Exception as e:
            self.error_occurred.emit(f"检测处理错误: {str(e)}")
            # 发生错误时仍然将原始帧放入队列
            try:
                error_data = {
                    'frame': frame.copy(),
                    'detections': [],
                    'counting_line': self.counting_line,
                    'line_direction': self.line_direction
                }
                self.detection_queue.put(error_data, timeout=0.01)
            except queue.Full:
                pass


class YOLODetectionApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YOLOv11 对象检测系统")
        self.setGeometry(100, 100, 1200, 800)

        # 初始化模型相关属性
        self.current_model_type = "PyTorch (.pt)"  # 默认模型类型
        self.model = None
        self.worker = None
        self.thread = None
        
        # 加载默认YOLO模型
        self.load_model()
        
        # 创建检测线程和工作器
        self.setup_worker()

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.is_paused = False

        self.init_ui()

    def load_model(self):
        """根据当前选择的模型类型加载模型"""
        try:
            if self.current_model_type == "PyTorch (.pt)":
                model_path = get_resource_path("best.pt")
            else:  # ONNX (.onnx)
                model_path = get_resource_path("best.onnx")
            
            self.model = YOLO(model_path)
            print(f"成功加载模型: {model_path}")
        except Exception as e:
            print(f"加载模型失败: {e}")
            # 如果ONNX模型加载失败，回退到PyTorch模型
            if self.current_model_type == "ONNX (.onnx)":
                print("回退到PyTorch模型")
                self.current_model_type = "PyTorch (.pt)"
                model_path = get_resource_path("best.pt")
                self.model = YOLO(model_path)

    def setup_worker(self):
        """设置检测工作器和线程"""
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
        
        self.thread = QThread()
        self.worker = DetectionWorker(self.model)
        self.worker.moveToThread(self.thread)
        
        # 连接信号
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.image_ready.connect(self.update_image)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.status_changed.connect(self.update_status)
        
        # 不自动启动线程，等待用户点击开始检测

    def change_model(self):
        """切换模型类型"""
        new_model_type = self.model_combo.currentText()
        if new_model_type != self.current_model_type:
            # 停止当前检测
            if self.worker and self.worker.running:
                self.stop_detection()
            
            self.current_model_type = new_model_type
            self.load_model()
            self.setup_worker()
            
            self.update_status(f"已切换到 {new_model_type} 模型")

    def init_ui(self):
        # 创建主部件和布局
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # 控制面板
        control_group = QGroupBox("控制面板")
        control_layout = QHBoxLayout()

        self.source_combo = QComboBox()
        self.source_combo.addItems(["摄像头", "视频文件", "图片文件", "USB手机"])
        self.source_combo.currentIndexChanged.connect(self.reset_ui)

        # 模型类型选择
        self.model_combo = QComboBox()
        self.model_combo.addItems(["PyTorch (.pt)", "ONNX (.onnx)"])
        self.model_combo.currentIndexChanged.connect(self.change_model)

        self.start_btn = QPushButton("开始检测")
        self.start_btn.clicked.connect(self.start_detection)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_detection)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)

        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumWidth(300)
        self.status_label.setStyleSheet("font-weight: bold;")

        control_layout.addWidget(QLabel("输入源:"))
        control_layout.addWidget(self.source_combo)
        control_layout.addWidget(QLabel("模型类型:"))
        control_layout.addWidget(self.model_combo)
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        control_group.setLayout(control_layout)

        # 计数线控制面板
        line_control_group = QGroupBox("计数线控制")
        line_control_layout = QHBoxLayout()

        # 线位置滑块
        self.line_position_slider = QSlider(Qt.Horizontal)
        self.line_position_slider.setMinimum(0)
        self.line_position_slider.setMaximum(100)
        self.line_position_slider.setValue(50)  # 默认在中间
        self.line_position_slider.valueChanged.connect(self.update_line_position)

        # 线方向选择
        self.line_direction_combo = QComboBox()
        self.line_direction_combo.addItems(["水平线", "垂直线"])
        self.line_direction_combo.currentIndexChanged.connect(self.update_line_direction)

        # 重置计数按钮
        self.reset_counter_btn = QPushButton("重置计数")
        self.reset_counter_btn.clicked.connect(self.reset_counter)

        line_control_layout.addWidget(QLabel("线位置:"))
        line_control_layout.addWidget(self.line_position_slider)
        line_control_layout.addWidget(QLabel("线方向:"))
        line_control_layout.addWidget(self.line_direction_combo)
        line_control_layout.addWidget(self.reset_counter_btn)
        line_control_group.setLayout(line_control_layout)

        # 显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setText("等待输入...")
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #2C2C2C; 
                color: white; 
                font-size: 24px;
                border: 2px solid #444444;
                border-radius: 5px;
            }
        """)

        # 添加到主布局
        main_layout.addWidget(control_group)
        main_layout.addWidget(line_control_group)
        main_layout.addWidget(self.image_label)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def update_line_position(self):
        """更新计数线位置"""
        position = self.line_position_slider.value() / 100.0
        self.worker.set_line_position(position)

    def update_line_direction(self):
        """更新计数线方向"""
        direction = 'horizontal' if self.line_direction_combo.currentText() == "水平线" else 'vertical'
        self.worker.set_line_direction(direction)
        # 重置计数线，使其在下一帧重新初始化
        self.worker.counting_line = None

    def reset_counter(self):
        """重置计数器"""
        self.worker.reset_counter()

    def reset_ui(self):
        """当选择新的输入源时重置UI"""
        self.image_label.setText("等待输入...")
        self.image_label.setPixmap(QPixmap())
        self.update_status("就绪")

    def start_detection(self):
        source_type = self.source_combo.currentText()
        file_path = None

        if source_type == "视频文件":
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv)")
            if not file_path:
                return
            source_type = "video"

        elif source_type == "图片文件":
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择图片文件", "", "图片文件 (*.jpg *.png *.bmp *.jpeg)")
            if not file_path:
                return
            source_type = "image"

        elif source_type == "USB手机":
            source_type = "usb_phone"

        else:  # 摄像头
            source_type = "camera"

        # 设置新的检测任务
        self.worker.set_source(source_type, file_path)
        
        # 启动线程
        if not self.thread.isRunning():
            self.thread.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_detection(self):
        self.worker.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # 重置暂停状态
        if self.is_paused:
            self.pause_btn.setText("暂停")
            self.is_paused = False

    @pyqtSlot(np.ndarray)
    def update_image(self, rgb_image):
        """更新显示图像"""
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w

        # 创建QImage
        q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)

        if not q_img.isNull():
            pixmap = QPixmap.fromImage(q_img)
            # 自适应缩放保持宽高比
            scaled_pixmap = pixmap.scaled(
                self.image_label.width(),
                self.image_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        else:
            self.image_label.setText("无法显示图像")

    @pyqtSlot(str)
    def show_error(self, message):
        """显示错误信息"""
        # 记录到日志
        logger.error(message)
        # 更新状态栏而不是在画面上显示
        self.update_status(f"错误: {message}")
        # 不再在图像标签上显示错误信息
        # self.image_label.setText(message)  # 注释掉这行
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    @pyqtSlot(str)
    def update_status(self, message):
        """更新状态标签"""
        self.status_label.setText(message)

        # 添加状态颜色指示
        if "错误" in message:
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
        elif "检测" in message:
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: blue; font-weight: bold;")

    def toggle_pause(self):
        if not self.is_paused:
            self.worker.pause()
            self.pause_btn.setText("恢复")
            self.is_paused = True
        else:
            self.worker.resume()
            self.pause_btn.setText("暂停")
            self.is_paused = False

    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        # 停止USB服务器
        if hasattr(self.worker, 'usb_server_running') and self.worker.usb_server_running:
            self.worker.stop_usb_server()
        
        self.worker.running = False
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YOLODetectionApp()
    window.show()
    sys.exit(app.exec_())