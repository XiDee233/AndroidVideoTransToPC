package com.example.videotrans

import android.Manifest
import android.content.Context
import android.util.Log
import androidx.camera.core.*
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import android.hardware.camera2.CaptureRequest
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.rememberMultiplePermissionsState
import kotlinx.coroutines.launch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun CameraPreviewScreen(
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val coroutineScope = rememberCoroutineScope()
    
    // 权限状态
    val permissionsState = rememberMultiplePermissionsState(
        permissions = listOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO
        )
    )
    
    // 摄像头状态
    var isStreaming by remember { mutableStateOf(false) }
    var streamingStatus by remember { mutableStateOf("应用已启动 - 等待操作") }
    var frameCount by remember { mutableStateOf(0) }
    var errorMessage by remember { mutableStateOf("") }
    var debugInfo by remember { mutableStateOf("调试信息: 应用正常启动") }
    
    // 摄像头执行器和相机实例
    val cameraExecutor: ExecutorService = remember { Executors.newSingleThreadExecutor() }
    var camera by remember { mutableStateOf<Camera?>(null) }
    
    // 视频流传输器
    val videoStreamer = remember { VideoStreamer() }
    
    // 快门速度状态 (1/100 到 1/2000)
    var shutterSpeed by remember { mutableStateOf(500f) } // 默认1/500，在范围中间
    // ISO状态
    var isoValue by remember { mutableStateOf(400f) } // 默认ISO 400，在范围中间
    val scrollState = rememberScrollState()
    
    LaunchedEffect(Unit) {
        if (!permissionsState.allPermissionsGranted) {
            permissionsState.launchMultiplePermissionRequest()
        }
    }
    
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // 标题
        Text(
            text = "Android 摄像头 USB 流传输",
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 16.dp)
        )
        
        if (permissionsState.allPermissionsGranted) {
            // 摄像头预览
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(3f / 4f),
                shape = RoundedCornerShape(12.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 8.dp)
            ) {
                AndroidView(
                    factory = { ctx ->
                        PreviewView(ctx).apply {
                            setupCamera(ctx, lifecycleOwner, this, cameraExecutor, 
                                onCameraReady = { cam -> 
                                    camera = cam
                                    // 应用默认的快门速度和ISO设置
                                    try {
                                        val camera2Control = Camera2CameraControl.from(cam.cameraControl)
                                        val exposureTimeNanos = getShutterSpeedNanos(shutterSpeed)
                                        
                                        val captureRequestOptions = CaptureRequestOptions.Builder()
                                            .setCaptureRequestOption(
                                                CaptureRequest.CONTROL_AE_MODE,
                                                CaptureRequest.CONTROL_AE_MODE_OFF
                                            )
                                            .setCaptureRequestOption(
                                                CaptureRequest.SENSOR_EXPOSURE_TIME,
                                                exposureTimeNanos
                                            )
                                            .setCaptureRequestOption(
                                                CaptureRequest.SENSOR_SENSITIVITY,
                                                isoValue.toInt()
                                            )
                                            .build()
                                        
                                        camera2Control.captureRequestOptions = captureRequestOptions
                                        Log.d("CameraPreview", "默认设置已应用 - 快门速度: 1/${shutterSpeed.toInt()}, ISO: ${isoValue.toInt()}")
                                    } catch (e: Exception) {
                                        Log.e("CameraPreview", "应用默认相机设置失败", e)
                                    }
                                },
                                onImageAnalysis = { imageProxy ->
                                    if (isStreaming) {
                                        // 处理图像帧
                                        coroutineScope.launch {
                                            try {
                                                videoStreamer.sendFrame(imageProxy)
                                                frameCount++
                                                streamingStatus = "传输中 - 帧率正常"
                                                debugInfo = "调试: 成功发送第${frameCount}帧"
                                                errorMessage = ""
                                            } catch (e: Exception) {
                                                streamingStatus = "传输错误"
                                                errorMessage = "发送失败: ${e.message}"
                                                debugInfo = "调试: 第${frameCount}帧发送失败 - ${e.javaClass.simpleName}"
                                                Log.e("CameraPreview", "帧发送失败", e)
                                                isStreaming = false
                                            } finally {
                                                // 确保在处理完成后关闭ImageProxy
                                                imageProxy.close()
                                            }
                                        }
                                    } else {
                                        // 如果不在传输状态，直接关闭ImageProxy
                                        imageProxy.close()
                                    }
                                }
                            )
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // 状态信息
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = when {
                        errorMessage.isNotEmpty() -> Color(0xFFFF5722) // 红色表示错误
                        isStreaming -> Color(0xFF4CAF50) // 绿色表示正常传输
                        else -> Color(0xFF2196F3) // 蓝色表示待机
                    }
                )
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "状态: $streamingStatus",
                        color = Color.White,
                        fontWeight = FontWeight.Medium,
                        fontSize = 16.sp
                    )
                    if (isStreaming) {
                        Text(
                            text = "已传输帧数: $frameCount",
                            color = Color.White,
                            fontSize = 14.sp
                        )
                    }
                    if (errorMessage.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = errorMessage,
                            color = Color.White,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
            
            Spacer(modifier = Modifier.height(8.dp))
            
            // 调试信息
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF37474F))
            ) {
                Column(
                    modifier = Modifier.padding(12.dp)
                ) {
                    Text(
                        text = debugInfo,
                        color = Color(0xFFE0E0E0),
                        fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace
                    )
                    Text(
                        text = "时间: ${java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())}",
                        color = Color(0xFFBDBDBD),
                        fontSize = 10.sp,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(8.dp))
            
            // 控制按钮
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                Button(
                    onClick = {
                        coroutineScope.launch {
                            if (isStreaming) {
                                videoStreamer.stopStreaming()
                                isStreaming = false
                                streamingStatus = "已停止传输"
                                debugInfo = "调试: 用户手动停止传输"
                            } else {
                                try {
                                    debugInfo = "调试: 开始连接测试..."
                                    streamingStatus = "正在测试连接..."
                                    videoStreamer.startStreaming()
                                    isStreaming = true
                                    frameCount = 0
                                    streamingStatus = "连接成功 - 开始传输"
                                    debugInfo = "调试: 连接成功，开始传输帧"
                                    errorMessage = ""
                                } catch (e: Exception) {
                                    streamingStatus = "连接失败"
                                    errorMessage = "错误: ${e.message}"
                                    debugInfo = "调试: 连接失败 - ${e.javaClass.simpleName}: ${e.message}"
                                    Log.e("CameraPreview", "连接失败", e)
                                }
                            }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isStreaming) Color(0xFFFF5722) else Color(0xFF4CAF50)
                    ),
                    modifier = Modifier.weight(1f)
                ) {
                    Text(
                        text = if (isStreaming) "停止传输" else "开始传输",
                        color = Color.White
                    )
                }
                
                Spacer(modifier = Modifier.width(16.dp))
                
                Button(
                    onClick = {
                        frameCount = 0
                        errorMessage = ""
                        streamingStatus = "应用已重置 - 等待操作"
                        debugInfo = "调试: 用户重置应用状态"
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF2196F3)
                    ),
                    modifier = Modifier.weight(1f)
                ) {
                    Text(
                        text = "重置状态",
                        color = Color.White
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(8.dp))
             
             // 快门速度控制
             Card(
                 modifier = Modifier.fillMaxWidth(),
                 colors = CardDefaults.cardColors(containerColor = Color(0xFF607D8B))
             ) {
                 Column(
                     modifier = Modifier.padding(12.dp)
                 ) {
                    Text(
                        text = "快门速度: 1/${shutterSpeed.toInt()}",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                    Slider(
                         value = shutterSpeed,
                         onValueChange = { newSpeed ->
                             shutterSpeed = newSpeed
                             // 应用快门速度设置
                             camera?.let { cam ->
                                 try {
                                     val camera2Control = Camera2CameraControl.from(cam.cameraControl)
                                     val exposureTimeNanos = getShutterSpeedNanos(newSpeed)
                                     
                                     val captureRequestOptions = CaptureRequestOptions.Builder()
                                         .setCaptureRequestOption(
                                             CaptureRequest.CONTROL_AE_MODE,
                                             CaptureRequest.CONTROL_AE_MODE_OFF
                                         )
                                         .setCaptureRequestOption(
                                             CaptureRequest.SENSOR_EXPOSURE_TIME,
                                             exposureTimeNanos
                                         )
                                         .setCaptureRequestOption(
                                             CaptureRequest.SENSOR_SENSITIVITY,
                                             isoValue.toInt()
                                         )
                                         .build()
                                     
                                     camera2Control.captureRequestOptions = captureRequestOptions
                                     Log.d("CameraPreview", "快门速度已设置: 1/${newSpeed.toInt()}")
                                 } catch (e: Exception) {
                                     Log.e("CameraPreview", "设置快门速度失败", e)
                                 }
                             }
                         },
                         valueRange = 100f..2000f,
                         steps = 18, // 20个步长
                         colors = SliderDefaults.colors(
                             thumbColor = Color.White,
                             activeTrackColor = Color(0xFF4CAF50),
                             inactiveTrackColor = Color(0xFF37474F)
                         ),
                         modifier = Modifier.fillMaxWidth()
                     )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "1/100",
                            color = Color(0xFFBDBDBD),
                            fontSize = 12.sp
                        )
                        Text(
                            text = "1/2000",
                            color = Color(0xFFBDBDBD),
                            fontSize = 12.sp
                        )
                    }
                }
            }
            
            Spacer(modifier = Modifier.height(8.dp))
             
             // ISO控制
             Card(
                 modifier = Modifier.fillMaxWidth(),
                 colors = CardDefaults.cardColors(containerColor = Color(0xFF607D8B))
             ) {
                 Column(
                     modifier = Modifier.padding(12.dp)
                 ) {
                    Text(
                        text = "ISO: ${isoValue.toInt()}",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                    Slider(
                         value = isoValue,
                         onValueChange = { newIso ->
                             isoValue = newIso
                             // 应用ISO设置
                             camera?.let { cam ->
                                 try {
                                     val camera2Control = Camera2CameraControl.from(cam.cameraControl)
                                     val exposureTimeNanos = getShutterSpeedNanos(shutterSpeed)
                                     
                                     val captureRequestOptions = CaptureRequestOptions.Builder()
                                         .setCaptureRequestOption(
                                             CaptureRequest.CONTROL_AE_MODE,
                                             CaptureRequest.CONTROL_AE_MODE_OFF
                                         )
                                         .setCaptureRequestOption(
                                             CaptureRequest.SENSOR_EXPOSURE_TIME,
                                             exposureTimeNanos
                                         )
                                         .setCaptureRequestOption(
                                             CaptureRequest.SENSOR_SENSITIVITY,
                                             newIso.toInt()
                                         )
                                         .build()
                                     
                                     camera2Control.captureRequestOptions = captureRequestOptions
                                     Log.d("CameraPreview", "ISO已设置: ${newIso.toInt()}")
                                 } catch (e: Exception) {
                                     Log.e("CameraPreview", "设置ISO失败", e)
                                 }
                             }
                         },
                         valueRange = 50f..3200f,
                         steps = 20,
                         colors = SliderDefaults.colors(
                             thumbColor = Color.White,
                             activeTrackColor = Color(0xFF4CAF50),
                             inactiveTrackColor = Color(0xFF37474F)
                         ),
                         modifier = Modifier.fillMaxWidth()
                     )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "ISO 50",
                            color = Color(0xFFBDBDBD),
                            fontSize = 12.sp
                        )
                        Text(
                            text = "ISO 3200",
                            color = Color(0xFFBDBDBD),
                            fontSize = 12.sp
                        )
                    }
                }
            }
            
            Spacer(modifier = Modifier.height(8.dp))
           
        } else {
            // 权限请求界面
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFEB3B))
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "需要摄像头权限",
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF333333)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "请授予摄像头和录音权限以使用视频流功能",
                        fontSize = 14.sp,
                        color = Color(0xFF666666)
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(
                        onClick = {
                            permissionsState.launchMultiplePermissionRequest()
                        }
                    ) {
                        Text("请求权限")
                    }
                }
            }
        }
    }
}

// 将快门速度值转换为纳秒
private fun getShutterSpeedNanos(shutterSpeed: Float): Long {
    return (1_000_000_000L / shutterSpeed).toLong()
}

private fun setupCamera(
    context: Context,
    lifecycleOwner: LifecycleOwner,
    previewView: PreviewView,
    cameraExecutor: ExecutorService,
    onCameraReady: (Camera) -> Unit,
    onImageAnalysis: (ImageProxy) -> Unit
) {
    val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
    
    cameraProviderFuture.addListener({
        val cameraProvider = cameraProviderFuture.get()
        
        // 预览用例
        val preview = Preview.Builder().build().also {
            it.setSurfaceProvider(previewView.surfaceProvider)
        }
        
        // 图像分析用例
        val imageAnalyzer = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor, ImageAnalysis.Analyzer { imageProxy ->
                    onImageAnalysis(imageProxy)
                })
            }
        
        // 选择后置摄像头
        val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
        
        try {
            // 解绑所有用例
            cameraProvider.unbindAll()
            
            // 绑定用例到摄像头
            val camera = cameraProvider.bindToLifecycle(
                lifecycleOwner,
                cameraSelector,
                preview,
                imageAnalyzer
            )
            
            // 通知相机已准备就绪
            onCameraReady(camera)
            
        } catch (exc: Exception) {
            Log.e("CameraPreview", "Use case binding failed", exc)
        }
        
    }, ContextCompat.getMainExecutor(context))
}