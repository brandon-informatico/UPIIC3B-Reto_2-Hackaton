package com.example.tiendas3b

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun EditCaptureScreen(capture: SavedCapture, onBack: () -> Unit, onChange: (PhotoType) -> Unit, onPickFacade: () -> Unit, busy: Boolean, message: String?) {
    BackHandler { onBack() }
    Scaffold { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text("Editar captura", style = MaterialTheme.typography.headlineSmall)
            Text("Elige la foto que quieres cambiar. La nueva foto se guarda al confirmarla.")
            TextButton(onClick = onBack, enabled = !busy) { Text("Volver al historial") }
            message?.let { Text(it) }
            listOf(
                PhotoType.LABEL to capture.label,
                PhotoType.PRODUCT to capture.product,
                PhotoType.STORE to capture.facade
            ).forEach { (type, path) ->
                OutlinedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(type.title, style = MaterialTheme.typography.titleMedium)
                        PhotoPreview(path, type.title, Modifier.fillMaxWidth().height(160.dp))
                        Button(onClick = { onChange(type) }, enabled = !busy) { Text("Tomar otra foto") }
                        if (type == PhotoType.STORE) {
                            OutlinedButton(onClick = onPickFacade, enabled = !busy) { Text("Elegir foto de fachada") }
                        }
                    }
                }
            }
        }
    }
}
