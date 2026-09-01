package com.company.betacenter.data

import kotlinx.coroutines.CancellationException
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.Closeable
import java.net.HttpURLConnection
import java.net.URL

class DownloadCallResourcesTest {
    @Test
    fun `cancellation closes both streams and disconnects the connection`() {
        val resources = DownloadCallResources()
        val connection = TrackingConnection()
        val input = TrackingCloseable()
        val output = TrackingCloseable()
        resources.attachConnection(connection)
        resources.attachInput(input)
        resources.attachOutput(output)

        resources.cancel()

        assertTrue(resources.isCancelled)
        assertTrue(connection.disconnected)
        assertTrue(input.closed)
        assertTrue(output.closed)
    }

    @Test
    fun `resource attached after cancellation is closed immediately`() {
        val resources = DownloadCallResources()
        val connection = TrackingConnection()
        val input = TrackingCloseable()
        resources.cancel()

        assertThrows(CancellationException::class.java) { resources.attachConnection(connection) }
        assertThrows(CancellationException::class.java) { resources.attachInput(input) }
        assertTrue(connection.disconnected)
        assertTrue(input.closed)
    }

    @Test
    fun `normal release does not mark the call cancelled`() {
        val resources = DownloadCallResources()
        val connection = TrackingConnection()
        resources.attachConnection(connection)

        resources.release()

        assertFalse(resources.isCancelled)
        assertTrue(connection.disconnected)
    }

    private class TrackingCloseable : Closeable {
        var closed = false
        override fun close() {
            closed = true
        }
    }

    private class TrackingConnection : HttpURLConnection(URL("https://example.test")) {
        var disconnected = false
        override fun connect() = Unit
        override fun usingProxy(): Boolean = false
        override fun disconnect() {
            disconnected = true
        }
    }
}
