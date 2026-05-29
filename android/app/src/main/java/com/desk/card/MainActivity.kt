package com.desk.card

import android.app.Activity
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Desk-card 设备端：全屏显示服务端渲染的 PNG，并在固定位置叠加本地时钟。
 *
 * 时钟用 TextView overlay 本地绘制（不烤进服务端图），位置/尺寸硬编码对齐服务端
 * PIL 绘制区：left=316 top=64 box 772×300、字号 280px。服务端图每分钟变化的只有
 * 慢数据，时钟由本地每分钟对齐刷新，并用 /etag.json 的 now_ms 校正设备时钟偏移
 * （K78W 的 RTC 已坏）。明文重建自反编译结果（原 MainActivity.kt 被 Esafenet 加密）。
 */
class MainActivity : Activity() {

    companion object {
        const val TIME_DRAW_LEFT = 316
        const val TIME_DRAW_TOP = 64
        const val TIME_BOX_WIDTH = 772
        const val TIME_BOX_HEIGHT = 300
        const val TIME_FONT_PX = 280f
    }

    private lateinit var image: ImageView
    private lateinit var status: TextView
    private lateinit var timeOverlay: TextView

    private val main = Handler(Looper.getMainLooper())
    private val ts = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    private val timeFmt = SimpleDateFormat("HH:mm", Locale.getDefault())

    @Volatile private var lastEtag = ""
    @Volatile private var stopFlag = false
    @Volatile private var serverReachable = false
    @Volatile private var serverTimeOffsetMs = 0L

    private fun currentServerTime(): Date =
        Date(System.currentTimeMillis() + serverTimeOffsetMs)

    // baseUrl 优先级：家里 LAN（这台 Mac 10.14.4.114 / 备用 .129）→ adb reverse 兜底 127.0.0.1。
    // 通了哪条就把 currentBase 锁到哪条。
    private val baseUrls = listOf(
        "http://10.14.4.114:8765",
        "http://10.14.4.129:8765",
        "http://127.0.0.1:8765",
    )
    @Volatile private var currentBase = baseUrls[0]

    private val pollIntervalMs = 180_000L   // 连得上时 3 min 轮询
    private val retryIntervalMs = 15_000L   // 连不上时 15s 快速重试

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )
        setContentView(R.layout.activity_main)
        image = findViewById(R.id.image)
        status = findViewById(R.id.status)
        timeOverlay = findViewById(R.id.time_overlay)
        configureTimeOverlay()
        setupExitGesture()
        startTimeTicker()
        startPolling()
    }

    /** 右上角（x>1154, y<250）长按 3s 退出 —— immersive 屏蔽不了的隐藏出口。 */
    private fun setupExitGesture() {
        val root = findViewById<FrameLayout>(R.id.root)
        val exitRunnable = Runnable {
            status.text = "exiting…"
            finishAndRemoveTask()
        }
        root.setOnTouchListener { _, ev ->
            when (ev.actionMasked) {
                MotionEvent.ACTION_DOWN ->
                    if (ev.x > 1154f && ev.y < 250f) {
                        status.text = "hold 3s to exit…"
                        main.postDelayed(exitRunnable, 3000L)
                    }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL ->
                    main.removeCallbacks(exitRunnable)
            }
            true
        }
    }

    override fun onDestroy() {
        stopFlag = true
        main.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    /** 时钟 overlay：280px 黑字白底、居中，定位到服务端图为它留出的 772×300 空区。 */
    private fun configureTimeOverlay() {
        timeOverlay.apply {
            setTextSize(TypedValue.COMPLEX_UNIT_PX, TIME_FONT_PX)
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
            setTextColor(Color.BLACK)
            setBackgroundColor(Color.WHITE)
            gravity = Gravity.CENTER
            text = "--:--"
        }
        timeOverlay.layoutParams = FrameLayout.LayoutParams(TIME_BOX_WIDTH, TIME_BOX_HEIGHT).apply {
            leftMargin = TIME_DRAW_LEFT
            topMargin = TIME_DRAW_TOP
        }
    }

    /** 每分钟对齐刷新本地时钟（用校正后的服务端时间）。 */
    private fun startTimeTicker() {
        main.post(object : Runnable {
            override fun run() {
                if (stopFlag) return
                timeOverlay.text = timeFmt.format(currentServerTime())
                val serverNow = System.currentTimeMillis() + serverTimeOffsetMs
                val delay = 60_000 - (serverNow % 60_000)
                main.postDelayed(this, delay)
            }
        })
    }

    /** 后台轮询线程：连得上 3 min、连不上 15s。 */
    private fun startPolling() {
        thread(name = "desk-card-poll") {
            while (!stopFlag) {
                try {
                    tick()
                } catch (e: Exception) {
                    val msg = e.message ?: e.javaClass.simpleName
                    main.post { status.text = "× " + msg.take(60) }
                }
                try {
                    Thread.sleep(if (serverReachable) pollIntervalMs else retryIntervalMs)
                } catch (e: InterruptedException) {
                    // ignore
                }
            }
        }
    }

    private fun tick() {
        val etagJson = fetchEtag()
        if (etagJson == null) {
            main.post { status.text = "× no server · " + ts.format(currentServerTime()) }
            return
        }
        val obj = JSONObject(etagJson)
        val etag = obj.optString("etag", "0")
        val exists = obj.optBoolean("exists", false)
        val nowMs = obj.optLong("now_ms", 0L)
        if (nowMs > 0) {
            serverTimeOffsetMs = nowMs - System.currentTimeMillis()
        }
        if (!exists) {
            main.post { status.text = "no image yet · " + ts.format(currentServerTime()) }
            return
        }
        if (etag != lastEtag) {
            val bytes = httpGetBytes("$currentBase/current.png")
            val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                ?: throw RuntimeException("decode failed")
            main.post {
                image.setImageBitmap(bmp)
                status.text = "↻ " + ts.format(currentServerTime()) + " · " +
                    currentBase.substringAfter("//").substringBefore(":")
            }
            lastEtag = etag
            return
        }
        main.post { status.text = "· " + ts.format(currentServerTime()) }
    }

    /** 按 currentBase 优先、其余 baseUrls 兜底，依次试 /etag.json；通了就锁定该 base。 */
    private fun fetchEtag(): String? {
        val ordered = listOf(currentBase) + baseUrls.filter { it != currentBase }
        for (base in ordered) {
            try {
                val json = httpGetString("$base/etag.json")
                currentBase = base
                serverReachable = true
                return json
            } catch (e: Exception) {
                // 试下一个 base
            }
        }
        serverReachable = false
        return null
    }

    private fun httpGetString(url: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 5000
        c.readTimeout = 5000
        try {
            return c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
    }

    private fun httpGetBytes(url: String): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 5000
        c.readTimeout = 10000
        try {
            return c.inputStream.use { it.readBytes() }
        } finally {
            c.disconnect()
        }
    }
}
