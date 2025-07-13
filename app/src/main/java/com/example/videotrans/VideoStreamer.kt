package com.example.videotrans

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.util.Log
import androidx.camera.core.ImageProxy
import kotlinx.coroutines.*
import kotlinx.coroutines.runBlocking
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.util.concurrent.TimeUnit

class VideoStreamer {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    
    private var isStreaming = false
    private var streamingJob: Job? = null
    
    // USB ADB端口转发地址 (需要在电脑上设置: adb forward tcp:8081 tcp:8081)
    private val serverUrl = "http://localhost:9001/upload_frame"
    
    companion object {
        private const val TAG = "VideoStreamer"
        private const val JPEG_QUALITY = 80
        private const val MAX_FRAME_SIZE = 1024 * 1024 // 1MB
    }
    
    fun startStreaming() {
        if (isStreaming) return
        
        Log.d(TAG, "开始连接测试...")
        
        // 测试连接
        if (testConnection()) {
            isStreaming = true
            Log.d(TAG, "连接测试成功，开始流传输")
        } else {
            Log.e(TAG, "连接测试失败")
            throw Exception("无法连接到Python服务器 (http://localhost:9001/ping)")
        }
    }
    
    fun stopStreaming() {
        isStreaming = false
        streamingJob?.cancel()
        Log.d(TAG, "停止视频流传输")
    }
    
    private fun testConnection(): Boolean {
        return try {
            Log.d(TAG, "测试连接到: http://localhost:9001/ping")
            
            // 使用runBlocking在IO线程中执行网络请求
            runBlocking(Dispatchers.IO) {
                val request = Request.Builder()
                    .url("http://localhost:9001/ping")
                    .build()
                
                val response = client.newCall(request).execute()
                val isSuccess = response.isSuccessful
                Log.d(TAG, "连接测试结果: $isSuccess, 响应码: ${response.code}")
                
                if (!isSuccess) {
                    Log.w(TAG, "服务器响应失败: ${response.code} ${response.message}")
                }
                
                response.close()
                isSuccess
            }
        } catch (e: Exception) {
            Log.e(TAG, "连接测试异常: ${e.javaClass.simpleName}: ${e.message}", e)
            false
        }
    }
    
    suspend fun sendFrame(imageProxy: ImageProxy) {
        if (!isStreaming) return
        
        try {
            // 将ImageProxy转换为JPEG字节数组
            val jpegBytes = imageProxyToJpegBytes(imageProxy)
            
            if (jpegBytes.size > MAX_FRAME_SIZE) {
                Log.w(TAG, "帧大小过大: ${jpegBytes.size} bytes，跳过此帧")
                return
            }
            
            // 发送到服务器
            sendFrameToServer(jpegBytes)
            
        } catch (e: Exception) {
            Log.e(TAG, "发送帧失败", e)
            // 不抛出异常，继续处理下一帧
        }
    }
    
    private suspend fun sendFrameToServer(jpegBytes: ByteArray) = withContext(Dispatchers.IO) {
        val requestBody = jpegBytes.toRequestBody("image/jpeg".toMediaType())
        
        val request = Request.Builder()
            .url(serverUrl)
            .post(requestBody)
            .addHeader("Content-Type", "image/jpeg")
            .addHeader("Frame-Timestamp", System.currentTimeMillis().toString())
            .build()
        
        try {
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                Log.w(TAG, "服务器响应错误: ${response.code}")
            }
            response.close()
        } catch (e: IOException) {
            Log.e(TAG, "网络请求失败", e)
            throw e
        }
    }
    
    private fun imageProxyToJpegBytes(imageProxy: ImageProxy): ByteArray {
        return when (imageProxy.format) {
            ImageFormat.YUV_420_888 -> {
                yuvToJpegBytes(imageProxy)
            }
            ImageFormat.JPEG -> {
                // 如果已经是JPEG格式，直接提取字节
                val buffer = imageProxy.planes[0].buffer
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                bytes
            }
            else -> {
                Log.w(TAG, "不支持的图像格式: ${imageProxy.format}，尝试YUV转换")
                yuvToJpegBytes(imageProxy)
            }
        }
    }
    
    private fun yuvToJpegBytes(imageProxy: ImageProxy): ByteArray {
        val yBuffer = imageProxy.planes[0].buffer
        val uBuffer = imageProxy.planes[1].buffer
        val vBuffer = imageProxy.planes[2].buffer
        
        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()
        
        val nv21 = ByteArray(ySize + uSize + vSize)
        
        // 复制Y平面
        yBuffer.get(nv21, 0, ySize)
        
        // 复制UV平面
        val uvPixelStride = imageProxy.planes[1].pixelStride
        if (uvPixelStride == 1) {
            uBuffer.get(nv21, ySize, uSize)
            vBuffer.get(nv21, ySize + uSize, vSize)
        } else {
            // 处理像素步长不为1的情况
            val uvBytes = ByteArray(uSize + vSize)
            uBuffer.get(uvBytes, 0, uSize)
            vBuffer.get(uvBytes, uSize, vSize)
            
            // 交错UV数据
            var uvIndex = ySize
            for (i in 0 until uSize step uvPixelStride) {
                nv21[uvIndex++] = uvBytes[i + uSize] // V
                nv21[uvIndex++] = uvBytes[i] // U
            }
        }
        
        // 转换为JPEG
        val yuvImage = YuvImage(
            nv21,
            ImageFormat.NV21,
            imageProxy.width,
            imageProxy.height,
            null
        )
        
        val outputStream = ByteArrayOutputStream()
        yuvImage.compressToJpeg(
            Rect(0, 0, imageProxy.width, imageProxy.height),
            JPEG_QUALITY,
            outputStream
        )
        
        return outputStream.toByteArray()
    }
    
    // 备用方法：通过Bitmap转换
    private fun imageProxyToBitmapJpeg(imageProxy: ImageProxy): ByteArray {
        val bitmap = imageProxyToBitmap(imageProxy)
        val outputStream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, outputStream)
        bitmap.recycle()
        return outputStream.toByteArray()
    }
    
    private fun imageProxyToBitmap(imageProxy: ImageProxy): Bitmap {
        val buffer = imageProxy.planes[0].buffer
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }
    
    fun getStreamingStatus(): String {
        return if (isStreaming) "传输中" else "未连接"
    }
    
    fun isCurrentlyStreaming(): Boolean {
        return isStreaming
    }
}

// 数据类用于传输帧信息
data class FrameData(
    val timestamp: Long,
    val width: Int,
    val height: Int,
    val format: String,
    val size: Int
)