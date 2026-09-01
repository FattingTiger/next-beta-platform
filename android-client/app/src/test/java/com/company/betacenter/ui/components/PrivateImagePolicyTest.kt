package com.company.betacenter.ui.components

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.IntSize
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class PrivateImagePolicyTest {
    @Test
    fun `fullscreen and thumbnail use independent cache keys`() {
        val url = "/api/v1/media/example"

        val thumbnail = privateImageCacheKey(url, PrivateImageResolution.Thumbnail)
        val fullScreen = privateImageCacheKey(url, PrivateImageResolution.FullScreen)

        assertNotEquals(thumbnail, fullScreen)
        assertEquals(thumbnail, privateImageCacheKey(url, PrivateImageResolution.Thumbnail))
    }

    @Test
    fun `fullscreen decode retains more source detail`() {
        val thumbnailSample = calculateImageSampleSize(
            sourceWidth = 4_000,
            sourceHeight = 3_000,
            limits = ImageDecodeLimits(maximumEdge = 1_280, maximumPixels = 1_500_000L),
        )
        val fullScreenSample = calculateImageSampleSize(
            sourceWidth = 4_000,
            sourceHeight = 3_000,
            limits = ImageDecodeLimits(maximumEdge = 2_560, maximumPixels = 3_500_000L),
        )

        assertEquals(4, thumbnailSample)
        assertEquals(2, fullScreenSample)
    }

    @Test
    fun `decode policy caps a fullscreen bitmap to a fraction of heap`() {
        val limits = imageDecodeLimits(
            resolution = PrivateImageResolution.FullScreen,
            maximumRuntimeMemoryBytes = 64L * 1024L * 1024L,
        )

        assertEquals(2_560, limits.maximumEdge)
        assertEquals(524_288L, limits.maximumPixels)
    }

    @Test
    fun `pan is clamped to the scaled viewport`() {
        val bounded = boundedImageOffset(
            proposed = Offset(5_000f, -5_000f),
            scale = 3f,
            viewportSize = IntSize(width = 1_000, height = 800),
        )

        assertEquals(Offset(1_000f, -800f), bounded)
    }

    @Test
    fun `unit scale and invalid coordinates reset pan`() {
        assertEquals(
            Offset.Zero,
            boundedImageOffset(
                proposed = Offset(120f, 80f),
                scale = 1f,
                viewportSize = IntSize(width = 1_000, height = 800),
            ),
        )
        assertEquals(
            Offset(0f, 80f),
            boundedImageOffset(
                proposed = Offset(Float.NaN, 80f),
                scale = 2f,
                viewportSize = IntSize(width = 1_000, height = 800),
            ),
        )
    }

    @Test
    fun `letterboxed image cannot be panned into empty vertical space`() {
        val bounded = boundedImageOffset(
            proposed = Offset(5_000f, 5_000f),
            scale = 2f,
            viewportSize = IntSize(width = 1_000, height = 800),
            imageSize = IntSize(width = 2_000, height = 500),
        )

        assertEquals(Offset(500f, 0f), bounded)
    }
}
