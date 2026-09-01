package com.company.betacenter.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Phone
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.company.betacenter.ui.components.AuroraBackdrop
import com.company.betacenter.ui.components.InlineMessage
import com.company.betacenter.ui.components.LensSurface

@Composable
fun LoginScreen(
    busy: Boolean,
    message: String?,
    messageIsError: Boolean,
    onLogin: (String, String) -> Unit,
    onDismissMessage: () -> Unit,
) {
    // Credentials deliberately stay out of SavedState/Bundle persistence.
    var phone by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var revealPassword by remember { mutableStateOf(false) }
    val passwordFocus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current

    Box(Modifier.fillMaxSize()) {
        AuroraBackdrop(Modifier.fillMaxWidth().height(320.dp).align(Alignment.TopCenter))
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = 22.dp, vertical = 44.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Column(Modifier.widthIn(max = 520.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("内测中心", style = MaterialTheme.typography.displaySmall)
                Spacer(Modifier.height(8.dp))
                Text(
                    "进入属于你测试组的应用版本",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(30.dp))
                LensSurface(Modifier.fillMaxWidth(), PaddingValues(24.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        Text("登录", style = MaterialTheme.typography.headlineMedium)
                        Text(
                            "账户由管理员创建，并与手机号绑定。",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (message != null) {
                            InlineMessage(
                                message,
                                isError = messageIsError,
                                actionLabel = "关闭",
                                onAction = onDismissMessage,
                            )
                        }
                        OutlinedTextField(
                            value = phone,
                            onValueChange = { if (it.length <= 24) phone = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("绑定手机号") },
                            leadingIcon = { Icon(Icons.Rounded.Phone, null) },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Phone,
                                imeAction = ImeAction.Next,
                            ),
                            keyboardActions = KeyboardActions(onNext = { passwordFocus.requestFocus() }),
                        )
                        OutlinedTextField(
                            value = password,
                            onValueChange = { if (it.length <= 128) password = it },
                            modifier = Modifier.fillMaxWidth().focusRequester(passwordFocus),
                            label = { Text("密码") },
                            leadingIcon = { Icon(Icons.Rounded.Lock, null) },
                            trailingIcon = {
                                IconButton(onClick = { revealPassword = !revealPassword }) {
                                    Icon(
                                        if (revealPassword) Icons.Rounded.Info else Icons.Rounded.Lock,
                                        contentDescription = if (revealPassword) "隐藏密码" else "显示密码",
                                    )
                                }
                            },
                            singleLine = true,
                            visualTransformation = if (revealPassword) VisualTransformation.None else PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Password,
                                imeAction = ImeAction.Done,
                            ),
                            keyboardActions = KeyboardActions(onDone = {
                                focusManager.clearFocus()
                                if (phone.isNotBlank() && password.isNotBlank()) onLogin(phone, password)
                            }),
                        )
                        Button(
                            onClick = { onLogin(phone, password) },
                            enabled = phone.isNotBlank() && password.isNotBlank() && !busy,
                            modifier = Modifier.fillMaxWidth().height(52.dp),
                        ) {
                            if (busy) {
                                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                                Spacer(Modifier.size(8.dp))
                            }
                            Text(if (busy) "正在登录" else "登录")
                        }
                        Text(
                            "平台不会公开注册，也不会向第三方账户开放。",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun InitialPasswordScreen(
    displayName: String,
    busy: Boolean,
    message: String?,
    messageIsError: Boolean,
    onSubmit: (current: String, replacement: String) -> Unit,
    onDismissMessage: () -> Unit,
) {
    var current by remember { mutableStateOf("") }
    var replacement by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    val localError = when {
        replacement.isNotEmpty() && replacement.length < 10 -> "新密码至少需要 10 个字符"
        confirmation.isNotEmpty() && replacement != confirmation -> "两次输入的新密码不一致"
        else -> null
    }
    val ready = current.isNotBlank() && replacement.length >= 10 && replacement == confirmation

    Box(Modifier.fillMaxSize()) {
        AuroraBackdrop(Modifier.fillMaxWidth().height(320.dp).align(Alignment.TopCenter))
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            LensSurface(Modifier.fillMaxWidth().widthIn(max = 520.dp)) {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text("设置你的登录密码", style = MaterialTheme.typography.headlineMedium)
                    Text(
                        "$displayName，这是首次登录。完成改密后需要用新密码重新登录。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (message != null || localError != null) {
                        InlineMessage(
                            localError ?: message.orEmpty(),
                            isError = localError != null || messageIsError,
                            actionLabel = if (message != null) "关闭" else null,
                            onAction = onDismissMessage,
                        )
                    }
                    PasswordField("当前初始密码", current, { current = it })
                    PasswordField("新密码", replacement, { replacement = it })
                    PasswordField("再次输入新密码", confirmation, { confirmation = it })
                    Text(
                        "使用大小写字母、数字、符号中的至少三类。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(
                        onClick = { onSubmit(current, replacement) },
                        enabled = ready && !busy,
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) {
                        if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.size(if (busy) 8.dp else 0.dp))
                        Text(if (busy) "正在更新" else "更新密码")
                    }
                }
            }
        }
    }
}

@Composable
private fun PasswordField(label: String, value: String, onValueChange: (String) -> Unit) {
    var reveal by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = { if (it.length <= 128) onValueChange(it) },
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        singleLine = true,
        visualTransformation = if (reveal) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            IconButton(onClick = { reveal = !reveal }) {
                Icon(
                    if (reveal) Icons.Rounded.Info else Icons.Rounded.Lock,
                    contentDescription = if (reveal) "隐藏密码" else "显示密码",
                )
            }
        },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
    )
}
