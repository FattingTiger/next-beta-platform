package com.company.qa.playground

import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.animation.DecelerateInterpolator
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.TextView
import android.widget.Toast
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.min
import kotlin.math.roundToInt

class MainActivity : Activity() {
    private var recordedPasses = 0
    private var latestResult: QaResult? = null

    private lateinit var countValue: TextView
    private lateinit var resultCard: LinearLayout
    private lateinit var resultStatus: TextView
    private lateinit var resultCodePanel: LinearLayout
    private lateinit var resultCode: TextView
    private lateinit var resultHint: TextView
    private lateinit var resultVerdict: TextView
    private lateinit var resultMeta: TextView
    private lateinit var checksContainer: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        restoreState(savedInstanceState)
        setContentView(buildScreen())
        configureSystemBars()
        renderState(animate = false)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt(KEY_RECORDED_PASSES, recordedPasses)
        latestResult?.let { result ->
            outState.putLong(KEY_RESULT_TIME, result.createdAtMillis)
            outState.putInt(KEY_RESULT_PASSES, result.recordedPasses)
        }
    }

    private fun restoreState(savedInstanceState: Bundle?) {
        if (savedInstanceState == null) return
        recordedPasses = savedInstanceState.getInt(KEY_RECORDED_PASSES, 0)
        val resultTime = savedInstanceState.getLong(KEY_RESULT_TIME, -1L)
        if (resultTime >= 0L) {
            latestResult = QaResultGenerator.generate(
                recordedPasses = savedInstanceState.getInt(KEY_RESULT_PASSES, 0),
                createdAtMillis = resultTime,
            )
        }
    }

    @Suppress("DEPRECATION")
    private fun configureSystemBars() {
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.isNavigationBarContrastEnforced = false
            window.isStatusBarContrastEnforced = false
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
            window.insetsController?.setSystemBarsAppearance(
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            )
        } else {
            window.decorView.systemUiVisibility =
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or
                View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
    }

    private fun buildScreen(): View {
        val root = AuraBackgroundView(this)
        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            isVerticalScrollBarEnabled = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(32))
            addView(buildHeader())
            addView(space(28))
            addView(buildCounterCard())
            addView(space(16))
            addView(buildResultCard())
            addView(space(16))
            addView(buildActions())
            addView(space(28))
            addView(
                label(
                    text = "QA PLAYGROUND  ·  1.0.0 (1)",
                    sizeSp = 11f,
                    color = Palette.MUTED,
                    font = Fonts.MEDIUM,
                ).apply {
                    gravity = Gravity.CENTER
                    letterSpacing = 0.12f
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                },
                matchWrap(),
            )
        }
        scrollView.addView(
            content,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )

        val screenWidth = resources.displayMetrics.widthPixels
        val pageWidth = min(screenWidth, dp(680))
        root.addView(
            scrollView,
            FrameLayout.LayoutParams(pageWidth, ViewGroup.LayoutParams.MATCH_PARENT).apply {
                gravity = Gravity.CENTER_HORIZONTAL
            },
        )
        applySafeArea(root, scrollView)
        return root
    }

    private fun applySafeArea(root: View, scrollView: View) {
        root.setOnApplyWindowInsetsListener { _, insets ->
            val top: Int
            val bottom: Int
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars())
                top = bars.top
                bottom = bars.bottom
            } else {
                @Suppress("DEPRECATION")
                top = insets.systemWindowInsetTop
                @Suppress("DEPRECATION")
                bottom = insets.systemWindowInsetBottom
            }
            scrollView.setPadding(0, top, 0, bottom)
            insets
        }
        root.requestApplyInsets()
    }

    private fun buildHeader(): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL

            addView(
                TextView(this@MainActivity).apply {
                    text = getString(R.string.qa_badge)
                    textSize = 16f
                    setTextColor(Palette.MINT_LIGHT)
                    typeface = Fonts.BLACK
                    gravity = Gravity.CENTER
                    letterSpacing = 0.06f
                    background = rounded(Palette.INK, 18)
                    elevation = dp(4).toFloat()
                    contentDescription = "QA 试验场图标"
                },
                LinearLayout.LayoutParams(dp(58), dp(58)),
            )
            addView(space(14, horizontal = true))
            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(
                        label("QA 试验场", 25f, Palette.INK, Fonts.BLACK),
                        matchWrap(),
                    )
                    addView(space(3))
                    addView(
                        label("验证每一次分发与安装", 13f, Palette.MUTED, Fonts.REGULAR),
                        matchWrap(),
                    )
                },
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
            )
            addView(
                pill("内部测试", Palette.MINT_WASH, Palette.GREEN, 12f),
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    dp(34),
                ),
            )
        }
    }

    private fun buildCounterCard(): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(22), dp(22), dp(22))
            background = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(Palette.INK, Palette.DARK_GREEN),
            ).apply { cornerRadius = dp(26).toFloat() }
            elevation = dp(6).toFloat()
            clipToOutline = true

            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(
                        label("本轮验证", 13f, Palette.MINT_LIGHT, Fonts.MEDIUM).apply {
                            letterSpacing = 0.08f
                        },
                        LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
                    )
                    addView(
                        pill("SESSION 01", Palette.WHITE_12, Color.WHITE, 11f),
                        LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.WRAP_CONTENT,
                            dp(32),
                        ),
                    )
                },
                matchWrap(),
            )
            addView(space(22))
            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.BOTTOM
                    countValue = label("0", 58f, Color.WHITE, Fonts.BLACK).apply {
                        includeFontPadding = false
                        contentDescription = "当前通过记录 0 次"
                    }
                    addView(
                        countValue,
                        LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
                    )
                    addView(
                        label("次通过记录", 14f, Palette.WHITE_70, Fonts.REGULAR).apply {
                            setPadding(0, 0, 0, dp(9))
                        },
                        wrapWrap(),
                    )
                },
                matchWrap(),
            )
            addView(space(7))
            addView(
                label(
                    "点击记录一次交互通过，用于确认应用状态可以正确更新。",
                    13f,
                    Palette.WHITE_70,
                    Fonts.REGULAR,
                ).apply { setLineSpacing(0f, 1.18f) },
                matchWrap(),
            )
            addView(space(20))
            addView(
                actionButton(
                    text = "+  记录一次通过",
                    fill = Palette.MINT,
                    textColor = Palette.INK,
                    rippleColor = Palette.GREEN_28,
                ) {
                    recordPass()
                },
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54)),
            )
        }
    }

    private fun buildResultCard(): View {
        resultCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(20))
            background = surface(Palette.SURFACE, 24, Palette.OUTLINE)
            elevation = dp(3).toFloat()
            clipToOutline = true

            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(
                        label("测试结果", 18f, Palette.INK, Fonts.BOLD),
                        LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
                    )
                    resultStatus = pill("等待生成", Palette.NEUTRAL_WASH, Palette.MUTED, 12f)
                    addView(
                        resultStatus,
                        LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.WRAP_CONTENT,
                            dp(34),
                        ),
                    )
                },
                matchWrap(),
            )
            addView(space(18))

            resultCodePanel = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(16), dp(15), dp(16), dp(14))
                background = clickableSurface(Palette.CANVAS_DEEP, Palette.GREEN_18, 16)
                isClickable = false
                isFocusable = false
                contentDescription = "尚未生成结果编号"
                setOnClickListener { copyResultCode() }

                resultCode = label("尚未生成编号", 18f, Palette.INK, Fonts.BOLD).apply {
                    letterSpacing = 0.04f
                }
                addView(resultCode, matchWrap())
                addView(space(4))
                resultHint = label(
                    "完成测试后可轻触复制编号",
                    12f,
                    Palette.MUTED,
                    Fonts.REGULAR,
                )
                addView(resultHint, matchWrap())
            }
            addView(resultCodePanel, matchWrap())
            addView(space(17))

            resultVerdict = label("等待生成测试结果", 16f, Palette.INK, Fonts.BOLD)
            addView(resultVerdict, matchWrap())
            addView(space(4))
            resultMeta = label(
                "系统会检查安装、交互与结果输出。",
                13f,
                Palette.MUTED,
                Fonts.REGULAR,
            ).apply { setLineSpacing(0f, 1.15f) }
            addView(resultMeta, matchWrap())
            addView(space(16))

            checksContainer = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
            }
            addView(checksContainer, matchWrap())
        }
        return resultCard
    }

    private fun buildActions(): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(
                actionButton(
                    text = "生成测试结果",
                    fill = Palette.PRIMARY,
                    textColor = Color.WHITE,
                    rippleColor = Palette.WHITE_24,
                ) {
                    generateResult()
                },
                LinearLayout.LayoutParams(0, dp(54), 1f),
            )
            addView(space(12, horizontal = true))
            addView(
                actionButton(
                    text = "重置",
                    fill = Palette.SURFACE,
                    textColor = Palette.INK,
                    rippleColor = Palette.GREEN_18,
                    borderColor = Palette.OUTLINE_STRONG,
                ) {
                    confirmReset()
                },
                LinearLayout.LayoutParams(dp(102), dp(54)),
            )
        }
    }

    private fun recordPass() {
        if (recordedPasses >= MAX_PASSES) {
            Toast.makeText(this, "本轮记录已达到上限", Toast.LENGTH_SHORT).show()
            return
        }
        recordedPasses += 1
        renderState(animate = true)
        hapticConfirm()
    }

    private fun generateResult() {
        latestResult = QaResultGenerator.generate(recordedPasses, System.currentTimeMillis())
        renderState(animate = true)
        hapticConfirm()
        Toast.makeText(this, "测试结果已生成", Toast.LENGTH_SHORT).show()
    }

    private fun confirmReset() {
        if (recordedPasses == 0 && latestResult == null) {
            Toast.makeText(this, "当前无需重置", Toast.LENGTH_SHORT).show()
            return
        }

        val dialog = AlertDialog.Builder(this)
            .setTitle("重置本轮测试？")
            .setMessage("通过记录和已生成的结果将被清除。")
            .setNegativeButton("取消", null)
            .setPositiveButton("重置") { _, _ -> resetSession() }
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(Palette.ERROR)
        }
        dialog.show()
    }

    private fun resetSession() {
        recordedPasses = 0
        latestResult = null
        renderState(animate = true)
        Toast.makeText(this, "本轮测试已重置", Toast.LENGTH_SHORT).show()
    }

    private fun copyResultCode() {
        val result = latestResult ?: return
        val clipboard = getSystemService(ClipboardManager::class.java)
        clipboard.setPrimaryClip(ClipData.newPlainText("QA 测试结果编号", result.code))
        if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.S_V2) {
            Toast.makeText(this, "编号已复制", Toast.LENGTH_SHORT).show()
        }
        hapticConfirm()
    }

    private fun renderState(animate: Boolean) {
        countValue.text = getString(R.string.count_value, recordedPasses)
        countValue.contentDescription = "当前通过记录 $recordedPasses 次"

        val result = latestResult
        if (result == null) {
            resultCard.background = surface(Palette.SURFACE, 24, Palette.OUTLINE)
            stylePill(resultStatus, "等待生成", Palette.NEUTRAL_WASH, Palette.MUTED)
            resultCode.text = "尚未生成编号"
            resultHint.text = "完成测试后可轻触复制编号"
            resultCodePanel.isClickable = false
            resultCodePanel.isFocusable = false
            resultCodePanel.contentDescription = "尚未生成结果编号"
            resultVerdict.text = "等待生成测试结果"
            resultMeta.text = "系统会检查安装、交互与结果输出。"
            renderChecks(completedChecks = 0)
        } else {
            resultCard.background = surface(Palette.SUCCESS_SURFACE, 24, Palette.SUCCESS_OUTLINE)
            stylePill(resultStatus, result.verdict, Palette.MINT_WASH, Palette.GREEN)
            resultCode.text = result.code
            resultHint.text = "轻触复制结果编号"
            resultCodePanel.isClickable = true
            resultCodePanel.isFocusable = true
            resultCodePanel.contentDescription = "结果编号 ${result.code}，轻触复制"
            resultVerdict.text = result.verdict
            val time = SimpleDateFormat("MM-dd  HH:mm:ss", Locale.CHINA)
                .format(Date(result.createdAtMillis))
            resultMeta.text = getString(R.string.result_meta, time, result.recordedPasses)
            renderChecks(result.completedChecks)
        }

        if (animate) {
            pulse(countValue)
            resultCard.alpha = 0.78f
            resultCard.animate()
                .alpha(1f)
                .setDuration(220L)
                .setInterpolator(DecelerateInterpolator())
                .start()
        }
    }

    private fun renderChecks(completedChecks: Int) {
        checksContainer.removeAllViews()
        val checks = listOf(
            "安装链路" to "应用已成功启动",
            "结果输出" to "可以生成唯一测试编号",
            "交互状态" to if (recordedPasses > 0) "计数状态已更新" else "等待记录一次通过",
        )
        checks.forEachIndexed { index, (title, subtitle) ->
            checksContainer.addView(checkRow(title, subtitle, index < completedChecks), matchWrap())
            if (index < checks.lastIndex) checksContainer.addView(space(10))
        }
    }

    private fun checkRow(title: String, subtitle: String, complete: Boolean): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(
                label(
                    if (complete) "✓" else "·",
                    if (complete) 13f else 22f,
                    if (complete) Palette.GREEN else Palette.MUTED,
                    Fonts.BOLD,
                ).apply {
                    gravity = Gravity.CENTER
                    background = rounded(
                        if (complete) Palette.MINT_WASH else Palette.NEUTRAL_WASH,
                        12,
                    )
                    contentDescription = if (complete) "已通过" else "待完成"
                },
                LinearLayout.LayoutParams(dp(30), dp(30)),
            )
            addView(space(12, horizontal = true))
            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(label(title, 14f, Palette.INK, Fonts.MEDIUM), matchWrap())
                    addView(space(2))
                    addView(label(subtitle, 12f, Palette.MUTED, Fonts.REGULAR), matchWrap())
                },
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f),
            )
        }
    }

    private fun actionButton(
        text: String,
        fill: Int,
        textColor: Int,
        rippleColor: Int,
        borderColor: Int? = null,
        onClick: () -> Unit,
    ): Button {
        return Button(this).apply {
            this.text = text
            textSize = 14f
            setTextColor(textColor)
            typeface = Fonts.BOLD
            isAllCaps = false
            gravity = Gravity.CENTER
            minHeight = dp(48)
            minimumHeight = dp(48)
            minimumWidth = 0
            stateListAnimator = null
            letterSpacing = 0.01f
            background = clickableSurface(fill, rippleColor, 16, borderColor)
            setOnClickListener { onClick() }
        }
    }

    private fun label(
        text: String,
        sizeSp: Float,
        color: Int,
        font: Typeface,
    ): TextView {
        return TextView(this).apply {
            this.text = text
            textSize = sizeSp
            setTextColor(color)
            typeface = font
            includeFontPadding = false
        }
    }

    private fun pill(text: String, fill: Int, textColor: Int, sizeSp: Float): TextView {
        return label(text, sizeSp, textColor, Fonts.MEDIUM).apply {
            gravity = Gravity.CENTER
            setPadding(dp(12), 0, dp(12), 0)
            background = rounded(fill, 20)
        }
    }

    private fun stylePill(view: TextView, text: String, fill: Int, textColor: Int) {
        view.text = text
        view.setTextColor(textColor)
        view.background = rounded(fill, 20)
    }

    private fun surface(fill: Int, radiusDp: Int, stroke: Int): GradientDrawable {
        return rounded(fill, radiusDp).apply { setStroke(dp(1), stroke) }
    }

    private fun rounded(fill: Int, radiusDp: Int): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fill)
            cornerRadius = dp(radiusDp).toFloat()
        }
    }

    private fun clickableSurface(
        fill: Int,
        rippleColor: Int,
        radiusDp: Int,
        borderColor: Int? = null,
    ): RippleDrawable {
        val content = rounded(fill, radiusDp).apply {
            borderColor?.let { setStroke(dp(1), it) }
        }
        val mask = rounded(Color.WHITE, radiusDp)
        return RippleDrawable(ColorStateList.valueOf(rippleColor), content, mask)
    }

    private fun pulse(view: View) {
        AnimatorSet().apply {
            playTogether(
                ObjectAnimator.ofFloat(view, View.SCALE_X, 1f, 1.08f, 1f),
                ObjectAnimator.ofFloat(view, View.SCALE_Y, 1f, 1.08f, 1f),
            )
            duration = 220L
            interpolator = DecelerateInterpolator()
            start()
        }
    }

    private fun hapticConfirm() {
        val feedback = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            HapticFeedbackConstants.CONFIRM
        } else {
            HapticFeedbackConstants.VIRTUAL_KEY
        }
        window.decorView.performHapticFeedback(feedback)
    }

    private fun space(sizeDp: Int, horizontal: Boolean = false): Space {
        return Space(this).apply {
            layoutParams = if (horizontal) {
                LinearLayout.LayoutParams(dp(sizeDp), 1)
            } else {
                LinearLayout.LayoutParams(1, dp(sizeDp))
            }
        }
    }

    private fun matchWrap() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    )

    private fun wrapWrap() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.WRAP_CONTENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    )

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).roundToInt()
    }

    private class AuraBackgroundView(context: Context) : FrameLayout(context) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private var mintAura: RadialGradient? = null
        private var blueAura: RadialGradient? = null

        init {
            setWillNotDraw(false)
        }

        override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
            super.onSizeChanged(width, height, oldWidth, oldHeight)
            if (width == 0 || height == 0) return
            mintAura = RadialGradient(
                width * 0.88f,
                height * 0.03f,
                width * 0.78f,
                intArrayOf(Palette.AURA_MINT, Color.TRANSPARENT),
                null,
                Shader.TileMode.CLAMP,
            )
            blueAura = RadialGradient(
                width * 0.02f,
                height * 0.44f,
                width * 0.64f,
                intArrayOf(Palette.AURA_BLUE, Color.TRANSPARENT),
                null,
                Shader.TileMode.CLAMP,
            )
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            canvas.drawColor(Palette.CANVAS)
            if (width == 0 || height == 0) return

            paint.shader = mintAura
            canvas.drawCircle(width * 0.88f, height * 0.03f, width * 0.78f, paint)

            paint.shader = blueAura
            canvas.drawCircle(width * 0.02f, height * 0.44f, width * 0.64f, paint)
            paint.shader = null
        }
    }

    private object Fonts {
        val REGULAR: Typeface = Typeface.create("sans-serif", Typeface.NORMAL)
        val MEDIUM: Typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        val BOLD: Typeface = Typeface.create("sans-serif", Typeface.BOLD)
        val BLACK: Typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
    }

    private object Palette {
        val CANVAS = Color.rgb(241, 246, 244)
        val CANVAS_DEEP = Color.rgb(234, 241, 238)
        val SURFACE = Color.rgb(252, 254, 253)
        val SUCCESS_SURFACE = Color.rgb(248, 253, 251)
        val INK = Color.rgb(13, 36, 32)
        val DARK_GREEN = Color.rgb(20, 68, 59)
        val PRIMARY = Color.rgb(42, 88, 198)
        val GREEN = Color.rgb(0, 118, 93)
        val MINT = Color.rgb(86, 226, 190)
        val MINT_LIGHT = Color.rgb(197, 255, 239)
        val MINT_WASH = Color.rgb(220, 248, 239)
        val NEUTRAL_WASH = Color.rgb(235, 240, 238)
        val MUTED = Color.rgb(91, 107, 101)
        val OUTLINE = Color.rgb(222, 230, 226)
        val OUTLINE_STRONG = Color.rgb(193, 206, 200)
        val SUCCESS_OUTLINE = Color.rgb(192, 226, 214)
        val ERROR = Color.rgb(179, 38, 30)
        val WHITE_12 = Color.argb(31, 255, 255, 255)
        val WHITE_24 = Color.argb(61, 255, 255, 255)
        val WHITE_70 = Color.argb(179, 255, 255, 255)
        val GREEN_18 = Color.argb(46, 0, 118, 93)
        val GREEN_28 = Color.argb(71, 0, 81, 63)
        val AURA_MINT = Color.argb(108, 77, 219, 183)
        val AURA_BLUE = Color.argb(54, 74, 119, 225)
    }

    private companion object {
        const val KEY_RECORDED_PASSES = "recorded_passes"
        const val KEY_RESULT_TIME = "result_time"
        const val KEY_RESULT_PASSES = "result_passes"
        const val MAX_PASSES = 9_999
    }
}
