package com.company.betacenter.data

import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import okhttp3.Call
import okhttp3.Callback
import okhttp3.EventListener
import okhttp3.Request
import okhttp3.Response
import okio.Timeout
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import kotlin.reflect.KClass

class OkHttpCancellationTest {
    @Test
    fun `cancelling the coroutine cancels the in-flight OkHttp call`() = runTest {
        val call = AwaitingCall()
        val job = launch(start = CoroutineStart.UNDISPATCHED) {
            awaitOkHttpCall(call) { Unit }
        }

        assertTrue(call.enqueued)
        job.cancelAndJoin()

        assertTrue(call.cancelled)
    }

    private class AwaitingCall : Call {
        private var callback: Callback? = null
        var enqueued = false
            private set
        var cancelled = false
            private set

        override fun request(): Request = REQUEST

        override fun execute(): Response = throw IOException("This fake call only supports enqueue")

        override fun enqueue(responseCallback: Callback) {
            enqueued = true
            callback = responseCallback
        }

        override fun cancel() {
            cancelled = true
            callback?.onFailure(this, IOException("Canceled"))
        }

        override fun isExecuted(): Boolean = enqueued

        override fun isCanceled(): Boolean = cancelled

        override fun timeout(): Timeout = Timeout.NONE

        override fun addEventListener(eventListener: EventListener) = Unit

        override fun <T : Any> tag(type: KClass<T>): T? = null

        override fun <T> tag(type: Class<out T>): T? = null

        override fun <T : Any> tag(type: KClass<T>, computeIfAbsent: () -> T): T = computeIfAbsent()

        override fun <T : Any> tag(type: Class<T>, computeIfAbsent: () -> T): T = computeIfAbsent()

        override fun clone(): Call = AwaitingCall()

        private companion object {
            val REQUEST: Request = Request.Builder().url("https://example.invalid/").build()
        }
    }
}
