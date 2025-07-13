import requests
import cv2
import numpy as np
import imutils
import time

# 替换为你手机显示的URL，末尾添加"/shot.jpg"
# 常见的IP地址格式：
# - 如果手机和电脑在同一WiFi: http://192.168.1.xxx:8081/shot.jpg
# - 如果使用热点: http://192.168.43.xxx:8081/shot.jpg
url = "http://192.168.31.7:8081/shot.jpg"

print("正在尝试连接到安卓摄像头...")
print(f"URL: {url}")
print("\n请确保：")
print("1. 手机已安装并启动IP Webcam应用")
print("2. 手机和电脑连接到同一WiFi网络")
print("3. IP Webcam应用中已点击'Start Server'")
print("4. 检查手机显示的IP地址是否与代码中的URL匹配")
print("\n按Ctrl+C停止程序\n")

# 添加连接测试
try:
    print("测试连接...")
    test_resp = requests.get(url, timeout=5)
    if test_resp.status_code == 200:
        print("✓ 连接成功！开始视频流...")
    else:
        print(f"✗ 连接失败，状态码: {test_resp.status_code}")
except requests.exceptions.ConnectTimeout:
    print("✗ 连接超时！请检查：")
    print("  - IP地址是否正确")
    print("  - IP Webcam应用是否已启动")
    print("  - 手机和电脑是否在同一网络")
    input("\n按Enter键退出...")
    exit(1)
except requests.exceptions.ConnectionError:
    print("✗ 连接错误！请检查网络连接")
    input("\n按Enter键退出...")
    exit(1)
except Exception as e:
    print(f"✗ 未知错误: {e}")
    input("\n按Enter键退出...")
    exit(1)

try:
    while True:
        try:
            img_resp = requests.get(url, timeout=3)
            if img_resp.status_code == 200:
                img_arr = np.array(bytearray(img_resp.content), dtype=np.uint8)
                img = cv2.imdecode(img_arr, -1)
                if img is not None:
                    img = imutils.resize(img, width=1000, height=1800)
                    cv2.imshow("Android Camera Stream - 按ESC退出", img)
                else:
                    print("警告: 无法解码图像")
            else:
                print(f"警告: HTTP状态码 {img_resp.status_code}")
                
        except requests.exceptions.Timeout:
            print("警告: 请求超时，重试中...")
            time.sleep(0.1)
            continue
        except requests.exceptions.ConnectionError:
            print("错误: 连接丢失")
            break
        except Exception as e:
            print(f"错误: {e}")
            break
            
        # 按ESC退出
        if cv2.waitKey(1) == 27:
            break
            
except KeyboardInterrupt:
    print("\n程序被用户中断")
finally:
    cv2.destroyAllWindows()
    print("程序结束")