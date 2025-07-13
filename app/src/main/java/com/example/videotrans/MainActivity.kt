package com.example.videotrans

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.displayCutoutPadding
import androidx.compose.material3.Scaffold
import androidx.compose.ui.Modifier
import com.example.videotrans.ui.theme.VideoTransTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            VideoTransTheme {
                Scaffold(
                    modifier = Modifier
                        .fillMaxSize()
                        .statusBarsPadding() // 适配状态栏
                        .navigationBarsPadding() // 适配导航栏
                        .displayCutoutPadding() // 适配刘海屏
                ) { innerPadding ->
                    CameraPreviewScreen(
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}