package com.company.betacenter.security

import com.company.betacenter.data.AuthSession
import com.company.betacenter.data.UserProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionGenerationStoreTest {
    @Test
    fun `stale login response cannot replace a newer login`() {
        val fixture = Fixture()
        val signedOut = fixture.store.snapshot()
        val userB = fixture.store.beginSessionIfUnchanged(signedOut, session("user-b", "b-1"))

        assertNull(fixture.store.beginSessionIfUnchanged(signedOut, session("user-a", "a-1")))
        assertEquals(userB, fixture.store.snapshot())
    }

    @Test
    fun `refresh keeps account generation and rejects a stale token snapshot`() {
        val fixture = Fixture()
        val signedIn = fixture.signIn("user-a", "a-1")
        val refreshed = fixture.store.refreshIfCurrent(signedIn, session("user-a", "a-2"))

        assertEquals(signedIn.generation, refreshed?.generation)
        assertEquals("a-2", refreshed?.session?.accessToken)
        assertNull(fixture.store.refreshIfCurrent(signedIn, session("user-a", "a-stale")))
        assertEquals(refreshed, fixture.store.snapshot())
    }

    @Test
    fun `old account refresh and 401 clear cannot touch the next account`() {
        val fixture = Fixture()
        val oldAccount = fixture.signIn("user-a", "a-1")
        fixture.store.clearAndAdvance()
        val newAccount = fixture.store.beginSessionIfUnchanged(
            fixture.store.snapshot(),
            session("user-b", "b-1"),
        )

        assertNull(fixture.store.refreshIfCurrent(oldAccount, session("user-a", "a-2")))
        assertFalse(fixture.store.clearIfCurrent(oldAccount))
        assertEquals(newAccount, fixture.store.snapshot())
    }

    @Test
    fun `logout always advances generation even when already signed out`() {
        val fixture = Fixture()
        val first = fixture.store.snapshot()
        val cleared = fixture.store.clearAndAdvance()
        val second = fixture.store.snapshot()

        assertEquals(first, cleared)
        assertNull(second.session)
        assertTrue(second.generation > first.generation)
    }

    @Test
    fun `retirement is persisted before cleanup and invalidates old request snapshots`() {
        val fixture = Fixture()
        val active = fixture.signIn("user-a", "a-1")
        val retiring = fixture.store.retireCurrent()

        assertTrue(retiring?.retiring == true)
        assertEquals("user-a", retiring?.session?.user?.id)
        assertNull(fixture.store.refreshIfCurrent(active, session("user-a", "a-stale")))
        assertFalse(fixture.store.clearIfCurrent(active))
        assertEquals(retiring, fixture.store.snapshot())
    }

    @Test
    fun `worker refresh preserves retirement until final clear`() {
        val fixture = Fixture()
        fixture.signIn("user-a", "a-1")
        val retiring = requireNotNull(fixture.store.retireCurrent())
        val refreshed = fixture.store.refreshIfCurrent(retiring, session("user-a", "a-2"))

        assertTrue(refreshed?.retiring == true)
        assertEquals("a-2", refreshed?.session?.accessToken)
        fixture.store.clearAndAdvance()
        assertNull(fixture.store.snapshot().session)
        assertFalse(fixture.store.snapshot().retiring)
    }

    private class Fixture {
        private var persisted = SessionSnapshot(0L, null)
        val store = SessionGenerationStore(
            read = { persisted },
            write = { persisted = it },
        )

        fun signIn(userId: String, token: String): SessionSnapshot =
            requireNotNull(store.beginSessionIfUnchanged(store.snapshot(), session(userId, token)))
    }

    private companion object {
        fun session(userId: String, accessToken: String) = AuthSession(
            accessToken = accessToken,
            refreshToken = "$accessToken-refresh",
            expiresAtEpochMillis = 1_900_000_000_000L,
            user = UserProfile(
                id = userId,
                displayName = userId,
                phone = "+8613800000000",
                role = "tester",
                mustChangePassword = false,
                groupIds = emptyList(),
            ),
        )
    }
}
