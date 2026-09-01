package com.company.betacenter.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.core.content.edit
import com.company.betacenter.data.AuthSession
import com.company.betacenter.data.sessionToJson
import com.company.betacenter.data.storedSessionFromJson
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal data class SessionSnapshot(
    val generation: Long,
    val session: AuthSession?,
    val retiring: Boolean = false,
)

/**
 * Serializes session state transitions independently from the Android storage
 * implementation. Login and logout advance the generation; an access-token
 * refresh stays in the same generation and replaces only its exact snapshot.
 */
internal class SessionGenerationStore(
    private val read: () -> SessionSnapshot,
    private val write: (SessionSnapshot) -> Unit,
) {
    private val lock = Any()

    fun snapshot(): SessionSnapshot = synchronized(lock) { read() }

    fun beginSessionIfUnchanged(expected: SessionSnapshot, session: AuthSession): SessionSnapshot? =
        synchronized(lock) {
            val current = read()
            if (current != expected) return@synchronized null
            SessionSnapshot(nextGeneration(current.generation), session, retiring = false).also(write)
        }

    fun refreshIfCurrent(expected: SessionSnapshot, session: AuthSession): SessionSnapshot? =
        synchronized(lock) {
            val current = read()
            if (current != expected || expected.session == null) return@synchronized null
            SessionSnapshot(current.generation, session, retiring = current.retiring).also(write)
        }

    fun retireCurrent(): SessionSnapshot? = synchronized(lock) {
        val current = read()
        if (current.session == null) return@synchronized null
        if (current.retiring) return@synchronized current
        current.copy(retiring = true).also(write)
    }

    fun clearAndAdvance(): SessionSnapshot = synchronized(lock) {
        val previous = read()
        write(SessionSnapshot(nextGeneration(previous.generation), null, retiring = false))
        previous
    }

    fun clearIfCurrent(expected: SessionSnapshot): Boolean = synchronized(lock) {
        val current = read()
        if (current != expected) return@synchronized false
        write(SessionSnapshot(nextGeneration(current.generation), null, retiring = false))
        true
    }

    fun clearGenerationIfCurrent(generation: Long, userId: String): Boolean = synchronized(lock) {
        val current = read()
        if (current.generation != generation || current.session?.user?.id != userId) return@synchronized false
        write(SessionSnapshot(nextGeneration(current.generation), null, retiring = false))
        true
    }

    private fun nextGeneration(value: Long): Long = if (value == Long.MAX_VALUE) 0L else value + 1L
}

class SecureSessionStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val generations = SessionGenerationStore(::readSnapshot, ::writeSnapshot)

    internal fun snapshot(): SessionSnapshot = generations.snapshot()

    internal fun beginSessionIfUnchanged(expected: SessionSnapshot, session: AuthSession): SessionSnapshot? =
        generations.beginSessionIfUnchanged(expected, session)

    internal fun refreshIfCurrent(expected: SessionSnapshot, session: AuthSession): SessionSnapshot? =
        generations.refreshIfCurrent(expected, session)

    internal fun retireCurrent(): SessionSnapshot? = generations.retireCurrent()

    internal fun clearAndAdvance(): SessionSnapshot = generations.clearAndAdvance()

    internal fun clearIfCurrent(expected: SessionSnapshot): Boolean = generations.clearIfCurrent(expected)

    internal fun clearGenerationIfCurrent(generation: Long, userId: String): Boolean =
        generations.clearGenerationIfCurrent(generation, userId)

    fun load(): AuthSession? = snapshot().takeUnless { it.retiring }?.session

    internal fun loadRetiring(): AuthSession? = snapshot().takeIf { it.retiring }?.session

    internal fun loadRaw(): AuthSession? = snapshot().session

    private fun readSnapshot(): SessionSnapshot {
        val generation = preferences.getLong(GENERATION, 0L)
        val encoded = preferences.getString(SESSION, null) ?: return SessionSnapshot(generation, null)
        return runCatching {
            val parts = encoded.split('.', limit = 2)
            require(parts.size == 2)
            val iv = Base64.decode(parts[0], Base64.NO_WRAP)
            val ciphertext = Base64.decode(parts[1], Base64.NO_WRAP)
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
            }
            val plaintext = cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
            SessionSnapshot(
                generation = generation,
                session = storedSessionFromJson(JSONObject(plaintext)),
                retiring = preferences.getBoolean(RETIRING, false),
            )
        }.getOrElse {
            val next = if (generation == Long.MAX_VALUE) 0L else generation + 1L
            preferences.edit(commit = true) {
                remove(SESSION)
                remove(RETIRING)
                putLong(GENERATION, next)
            }
            SessionSnapshot(next, null)
        }
    }

    private fun writeSnapshot(snapshot: SessionSnapshot) {
        val encoded = snapshot.session?.let(::encrypt)
        preferences.edit(commit = true) {
            putLong(GENERATION, snapshot.generation)
            if (encoded == null) {
                remove(SESSION)
                remove(RETIRING)
            } else {
                putString(SESSION, encoded)
                if (snapshot.retiring) putBoolean(RETIRING, true) else remove(RETIRING)
            }
        }
    }

    private fun encrypt(session: AuthSession): String {
        val cipher = Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        }
        val ciphertext = cipher.doFinal(sessionToJson(session).toString().toByteArray(Charsets.UTF_8))
        return buildString {
            append(Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            append('.')
            append(Base64.encodeToString(ciphertext, Base64.NO_WRAP))
        }
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val PREFERENCES = "secure_session"
        const val SESSION = "session_blob"
        const val GENERATION = "session_generation"
        const val RETIRING = "session_retiring"
        const val KEY_ALIAS = "beta_center_session_v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
