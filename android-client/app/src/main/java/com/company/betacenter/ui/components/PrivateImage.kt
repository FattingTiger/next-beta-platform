package com.company.betacenter.ui.components

import android.graphics.BitmapFactory
import android.net.Uri
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.company.betacenter.data.BetaRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.InputStream
import java.util.Locale
import kotlin.math.abs

enum class PrivateImageResolution(
    internal val cacheTag: String,
    internal val maximumEdge: Int,
    internal val maximumPixels: Long,
) {
    Thumbnail(
        cacheTag = "thumbnail-v1",
        maximumEdge = 1_280,
        maximumPixels = 1_500_000L,
    ),
    FullScreen(
        cacheTag = "fullscreen-v1",
        maximumEdge = 2_560,
        maximumPixels = 3_500_000L,
    ),
}

internal data class ImageDecodeLimits(
    val maximumEdge: Int,
    val maximumPixels: Long,
)

private sealed interface ImageLoadState {
    data object Empty : ImageLoadState

    data object Loading : ImageLoadState

    data class Success(val bitmap: ImageBitmap) : ImageLoadState

    data class Error(val message: String) : ImageLoadState
}

private object MemoryImages {
    private val maxSizeKilobytes = minOf(
        16 * 1024,
        (Runtime.getRuntime().maxMemory() / 1024L / 16L).toInt(),
    ).coerceAtLeast(4 * 1024)
    private val values = object : LruCache<String, ImageBitmap>(maxSizeKilobytes) {
        override fun sizeOf(key: String, value: ImageBitmap): Int = imageSizeKilobytes(value)
    }

    fun get(key: String): ImageBitmap? = synchronized(values) { values.get(key) }

    fun put(key: String, bitmap: ImageBitmap) {
        if (imageSizeKilobytes(bitmap) > maxSizeKilobytes) return
        synchronized(values) { values.put(key, bitmap) }
    }

    fun clear() = synchronized(values) { values.evictAll() }

    private fun imageSizeKilobytes(value: ImageBitmap): Int =
        ((value.width.toLong() * value.height.toLong() * BYTES_PER_PIXEL) / 1024L)
            .coerceIn(1L, Int.MAX_VALUE.toLong())
            .toInt()
}

fun clearPrivateImageMemoryCache() = MemoryImages.clear()

@Composable
fun PrivateImage(
    repository: BetaRepository,
    relativeUrl: String?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    contentScale: ContentScale = ContentScale.Crop,
    cacheInMemory: Boolean = true,
    resolution: PrivateImageResolution = PrivateImageResolution.Thumbnail,
    onImageSize: (IntSize) -> Unit = {},
) {
    val cacheKey = remember(relativeUrl, resolution) {
        relativeUrl
            ?.takeIf(String::isNotBlank)
            ?.let { privateImageCacheKey(it, resolution) }
    }
    var retryAttempt by remember(relativeUrl, resolution) { mutableIntStateOf(0) }
    var loadState by remember(relativeUrl, resolution, cacheInMemory) {
        mutableStateOf(
            cacheKey
                ?.takeIf { cacheInMemory }
                ?.let(MemoryImages::get)
                ?.let(ImageLoadState::Success)
                ?: if (cacheKey == null) ImageLoadState.Empty else ImageLoadState.Loading,
        )
    }

    LaunchedEffect(relativeUrl, resolution, cacheInMemory, retryAttempt) {
        val url = relativeUrl?.takeIf(String::isNotBlank)
        if (url == null) {
            loadState = ImageLoadState.Empty
            return@LaunchedEffect
        }

        val key = privateImageCacheKey(url, resolution)
        if (cacheInMemory) {
            MemoryImages.get(key)?.let { cached ->
                loadState = ImageLoadState.Success(cached)
                return@LaunchedEffect
            }
        }

        loadState = ImageLoadState.Loading
        loadState = try {
            val bytes = repository.privateImage(url)
            val bitmap = withContext(Dispatchers.Default) {
                decodeSampled(bytes, resolution)
            } ?: throw IllegalArgumentException("图片内容无法解码")
            if (cacheInMemory) MemoryImages.put(key, bitmap)
            ImageLoadState.Success(bitmap)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            ImageLoadState.Error("加载失败，请重试")
        }
    }

    val currentOnImageSize by rememberUpdatedState(onImageSize)
    val successfulBitmap = (loadState as? ImageLoadState.Success)?.bitmap
    LaunchedEffect(successfulBitmap) {
        successfulBitmap?.let { bitmap ->
            currentOnImageSize(IntSize(bitmap.width, bitmap.height))
        }
    }

    RenderImageState(
        state = loadState,
        contentDescription = contentDescription,
        modifier = modifier,
        contentScale = contentScale,
        expandedFailure = resolution == PrivateImageResolution.FullScreen,
        onRetry = {
            loadState = ImageLoadState.Loading
            retryAttempt += 1
        },
    )
}

@Composable
fun LocalUriImage(
    uri: Uri,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    contentScale: ContentScale = ContentScale.Crop,
) {
    val context = LocalContext.current
    var retryAttempt by remember(uri) { mutableIntStateOf(0) }
    var loadState by remember(uri) { mutableStateOf<ImageLoadState>(ImageLoadState.Loading) }

    LaunchedEffect(uri, retryAttempt) {
        loadState = ImageLoadState.Loading
        loadState = try {
            val bitmap = withContext(Dispatchers.IO) {
                decodeSampled(
                    openStream = {
                        if (uri.scheme == "file") {
                            uri.path?.let { File(it).takeIf(File::isFile)?.inputStream() }
                        } else {
                            context.contentResolver.openInputStream(uri)
                        }
                    },
                    resolution = PrivateImageResolution.Thumbnail,
                )
            } ?: throw IllegalArgumentException("图片内容无法解码")
            ImageLoadState.Success(bitmap)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            ImageLoadState.Error("读取失败，请重试")
        }
    }

    RenderImageState(
        state = loadState,
        contentDescription = contentDescription,
        modifier = modifier,
        contentScale = contentScale,
        expandedFailure = false,
        onRetry = {
            loadState = ImageLoadState.Loading
            retryAttempt += 1
        },
    )
}

@Composable
private fun RenderImageState(
    state: ImageLoadState,
    contentDescription: String?,
    modifier: Modifier,
    contentScale: ContentScale,
    expandedFailure: Boolean,
    onRetry: () -> Unit,
) {
    when (state) {
        ImageLoadState.Empty -> EmptyImagePlaceholder(modifier, contentDescription)
        ImageLoadState.Loading -> ImageLoadingPlaceholder(modifier, contentDescription)
        is ImageLoadState.Error -> ImageFailurePlaceholder(
            modifier = modifier,
            contentDescription = contentDescription,
            message = state.message,
            expanded = expandedFailure,
            onRetry = onRetry,
        )
        is ImageLoadState.Success -> Image(
            bitmap = state.bitmap,
            contentDescription = contentDescription,
            modifier = modifier,
            contentScale = contentScale,
        )
    }
}

@Composable
private fun EmptyImagePlaceholder(modifier: Modifier, contentDescription: String?) {
    Box(
        modifier = modifier.background(MaterialTheme.colorScheme.primaryContainer),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = Icons.Rounded.Build,
            contentDescription = contentDescription,
            tint = MaterialTheme.colorScheme.onPrimaryContainer,
            modifier = Modifier.fillMaxSize(0.46f),
        )
    }
}

@Composable
private fun ImageLoadingPlaceholder(modifier: Modifier, contentDescription: String?) {
    val label = contentDescription?.let { "$it，正在加载" } ?: "图片正在加载"
    Box(
        modifier = modifier
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .semantics { this.contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(
            modifier = Modifier.size(28.dp),
            color = MaterialTheme.colorScheme.primary,
            strokeWidth = 2.dp,
        )
    }
}

@Composable
private fun ImageFailurePlaceholder(
    modifier: Modifier,
    contentDescription: String?,
    message: String,
    expanded: Boolean,
    onRetry: () -> Unit,
) {
    val retryDescription = contentDescription?.let { "$it，加载失败，重试" } ?: "图片加载失败，重试"
    BoxWithConstraints(
        modifier = modifier.background(MaterialTheme.colorScheme.errorContainer),
        contentAlignment = Alignment.Center,
    ) {
        val showMessage = expanded || (maxWidth >= 120.dp && maxHeight >= 88.dp)
        if (showMessage) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = message,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    style = MaterialTheme.typography.bodyMedium,
                )
                TextButton(onClick = onRetry) {
                    Icon(Icons.Rounded.Refresh, contentDescription = null)
                    Text("重试", Modifier.padding(start = 6.dp))
                }
            }
        } else {
            IconButton(onClick = onRetry) {
                Icon(
                    imageVector = Icons.Rounded.Refresh,
                    contentDescription = retryDescription,
                    tint = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
        }
    }
}

@Composable
fun PrivateImageDialog(
    repository: BetaRepository,
    relativeUrl: String,
    contentDescription: String,
    onDismiss: () -> Unit,
) {
    var scale by remember(relativeUrl) { mutableFloatStateOf(MIN_IMAGE_SCALE) }
    var offset by remember(relativeUrl) { mutableStateOf(Offset.Zero) }
    var viewportSize by remember(relativeUrl) { mutableStateOf(IntSize.Zero) }
    var imageSize by remember(relativeUrl) { mutableStateOf(IntSize.Zero) }

    fun resetTransform() {
        scale = MIN_IMAGE_SCALE
        offset = Offset.Zero
    }

    val transformState = rememberTransformableState { zoomChange, panChange, _ ->
        val proposedScale = (scale * zoomChange)
            .takeIf { it.isFinite() }
            ?.coerceIn(MIN_IMAGE_SCALE, MAX_IMAGE_SCALE)
            ?: scale
        offset = if (abs(proposedScale - MIN_IMAGE_SCALE) < SCALE_EPSILON) {
            Offset.Zero
        } else {
            boundedImageOffset(offset + panChange, proposedScale, viewportSize, imageSize)
        }
        scale = proposedScale
    }

    LaunchedEffect(viewportSize, imageSize, scale) {
        offset = boundedImageOffset(offset, scale, viewportSize, imageSize)
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false),
    ) {
        Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Color(0xF2161B19))) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 18.dp, vertical = 72.dp)
                    .clipToBounds()
                    .onSizeChanged { viewportSize = it }
                    .pointerInput(relativeUrl) {
                        detectTapGestures(
                            onDoubleTap = {
                                if (scale > MIN_IMAGE_SCALE + SCALE_EPSILON) {
                                    resetTransform()
                                } else {
                                    scale = DOUBLE_TAP_IMAGE_SCALE
                                    offset = Offset.Zero
                                }
                            },
                        )
                    }
                    .transformable(transformState),
                contentAlignment = Alignment.Center,
            ) {
                PrivateImage(
                    repository = repository,
                    relativeUrl = relativeUrl,
                    contentDescription = contentDescription,
                    modifier = Modifier
                        .fillMaxSize()
                        .graphicsLayer(
                            scaleX = scale,
                            scaleY = scale,
                            translationX = offset.x,
                            translationY = offset.y,
                        ),
                    contentScale = ContentScale.Fit,
                    resolution = PrivateImageResolution.FullScreen,
                    onImageSize = { imageSize = it },
                )
            }
            Surface(
                modifier = Modifier.align(Alignment.TopStart).statusBarsPadding().padding(16.dp),
                color = androidx.compose.ui.graphics.Color(0xCC2A332F),
                contentColor = androidx.compose.ui.graphics.Color.White,
                shape = CompactShape,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "双指/双击 · ${scale.formatScale()}",
                        modifier = Modifier.padding(start = 12.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
                    )
                    if (scale > MIN_IMAGE_SCALE + SCALE_EPSILON) {
                        IconButton(onClick = ::resetTransform, modifier = Modifier.size(40.dp)) {
                            Icon(Icons.Rounded.Refresh, contentDescription = "复位大图")
                        }
                    }
                }
            }
            IconButton(
                onClick = onDismiss,
                modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(12.dp),
            ) {
                Icon(
                    Icons.Rounded.Close,
                    contentDescription = "关闭大图",
                    tint = androidx.compose.ui.graphics.Color.White,
                )
            }
        }
    }
}

internal fun privateImageCacheKey(relativeUrl: String, resolution: PrivateImageResolution): String =
    "${resolution.cacheTag}:$relativeUrl"

internal fun calculateImageSampleSize(
    sourceWidth: Int,
    sourceHeight: Int,
    limits: ImageDecodeLimits,
): Int {
    require(sourceWidth > 0 && sourceHeight > 0) { "source dimensions must be positive" }
    require(limits.maximumEdge > 0 && limits.maximumPixels > 0L) { "decode limits must be positive" }

    var sample = 1
    while (
        sourceWidth / sample > limits.maximumEdge ||
        sourceHeight / sample > limits.maximumEdge ||
        (sourceWidth.toLong() / sample) * (sourceHeight.toLong() / sample) > limits.maximumPixels
    ) {
        sample *= 2
    }
    return sample
}

internal fun boundedImageOffset(
    proposed: Offset,
    scale: Float,
    viewportSize: IntSize,
    imageSize: IntSize = viewportSize,
): Offset {
    if (
        !scale.isFinite() ||
        scale <= MIN_IMAGE_SCALE + SCALE_EPSILON ||
        viewportSize.width <= 0 ||
        viewportSize.height <= 0
    ) {
        return Offset.Zero
    }

    val validImageSize = imageSize.takeIf { it.width > 0 && it.height > 0 } ?: viewportSize
    val fitScale = minOf(
        viewportSize.width.toFloat() / validImageSize.width,
        viewportSize.height.toFloat() / validImageSize.height,
    )
    val displayedWidth = validImageSize.width * fitScale
    val displayedHeight = validImageSize.height * fitScale
    val maximumX = ((displayedWidth * scale - viewportSize.width) / 2f).coerceAtLeast(0f)
    val maximumY = ((displayedHeight * scale - viewportSize.height) / 2f).coerceAtLeast(0f)
    val safeX = proposed.x.takeIf { it.isFinite() } ?: 0f
    val safeY = proposed.y.takeIf { it.isFinite() } ?: 0f
    return Offset(
        x = safeX.coerceIn(-maximumX, maximumX),
        y = safeY.coerceIn(-maximumY, maximumY),
    )
}

private fun Float.formatScale(): String = String.format(Locale.ROOT, "%.1f×", this)

private fun decodeSampled(
    bytes: ByteArray,
    resolution: PrivateImageResolution,
): ImageBitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    val options = decodeOptions(bounds, resolution) ?: return null
    return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)?.asImageBitmap()
}

private fun decodeSampled(
    openStream: () -> InputStream?,
    resolution: PrivateImageResolution,
): ImageBitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    openStream()?.use { BitmapFactory.decodeStream(it, null, bounds) } ?: return null
    val options = decodeOptions(bounds, resolution) ?: return null
    return openStream()?.use { BitmapFactory.decodeStream(it, null, options)?.asImageBitmap() }
}

private fun decodeOptions(
    bounds: BitmapFactory.Options,
    resolution: PrivateImageResolution,
): BitmapFactory.Options? {
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    val limits = imageDecodeLimits(resolution)
    return BitmapFactory.Options().apply {
        inSampleSize = calculateImageSampleSize(bounds.outWidth, bounds.outHeight, limits)
        inPreferredConfig = android.graphics.Bitmap.Config.ARGB_8888
    }
}

internal fun imageDecodeLimits(
    resolution: PrivateImageResolution,
    maximumRuntimeMemoryBytes: Long = Runtime.getRuntime().maxMemory(),
): ImageDecodeLimits {
    val runtimePixelBudget =
        (maximumRuntimeMemoryBytes / MEMORY_FRACTION_FOR_ONE_BITMAP / BYTES_PER_PIXEL)
            .coerceAtLeast(1L)
    return ImageDecodeLimits(
        maximumEdge = resolution.maximumEdge,
        maximumPixels = minOf(resolution.maximumPixels, runtimePixelBudget),
    )
}

private const val BYTES_PER_PIXEL = 4L
private const val MEMORY_FRACTION_FOR_ONE_BITMAP = 32L
private const val MIN_IMAGE_SCALE = 1f
private const val DOUBLE_TAP_IMAGE_SCALE = 2f
private const val MAX_IMAGE_SCALE = 5f
private const val SCALE_EPSILON = 0.001f
