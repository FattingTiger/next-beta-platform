package com.company.betacenter.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ExitToApp
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Phone
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.company.betacenter.data.UserProfile
import com.company.betacenter.ui.components.ContentSurface
import com.company.betacenter.ui.components.LensSurface

@Composable
fun ProfileScreen(user: UserProfile, onLogout: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, top = 34.dp, end = 20.dp, bottom = 30.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        item {
            Text("我的", style = MaterialTheme.typography.headlineLarge)
            Text("账户由管理员维护", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            LensSurface(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(user.displayName, style = MaterialTheme.typography.headlineMedium)
                    Text(if (user.role == "admin") "平台管理员" else "内测用户", color = MaterialTheme.colorScheme.primary)
                    Text(user.phone, style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
        item {
            ContentSurface(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    ProfileFact(Icons.Rounded.Phone, "绑定手机号", user.phone)
                    ProfileFact(Icons.Rounded.Person, "测试组", "已加入 ${user.groupIds.size} 个测试组")
                    ProfileFact(Icons.Rounded.Lock, "分发范围", "仅可查看管理员授权的应用")
                }
            }
        }
        item {
            OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.AutoMirrored.Rounded.ExitToApp, null)
                Spacer(Modifier.size(8.dp))
                Text("退出登录")
            }
        }
    }
}

@Composable
private fun ProfileFact(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
        Column {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.bodyLarge)
        }
    }
}
