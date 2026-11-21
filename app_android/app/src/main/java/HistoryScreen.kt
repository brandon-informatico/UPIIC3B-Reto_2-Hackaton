package com.example.tiendas3b

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import java.text.DateFormat
import java.util.Date
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun PhotoPreview(path: String, description: String, modifier: Modifier = Modifier) {
    val bitmap by produceState<Bitmap?>(initialValue = null, path) {
        value = withContext(Dispatchers.IO) { loadPreview(path) }
    }
    val image = bitmap
    if (image == null) Text("No se pudo mostrar la foto", modifier = modifier)
    else Image(image.asImageBitmap(), description, modifier)
}

@Composable
fun HistoryScreen(captures: List<SavedCapture>, onBack: () -> Unit, onExport: (SavedCapture) -> Unit, onDelete: (String) -> Unit, onEdit: (String) -> Unit, message: String?, busy: Boolean) {
    var pendingDelete by rememberSaveable { mutableStateOf<String?>(null) }
    BackHandler { onBack() }
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Image(
            painter = painterResource(R.drawable.fondo_app),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Fit,
            alpha = 0.12f
        )
        Scaffold(containerColor = Color.Transparent) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Historial de capturas", style = MaterialTheme.typography.headlineSmall)
            TextButton(onClick = onBack) { Text("Volver") }
            message?.let { Text(it) }
            if (captures.isEmpty()) Text("Aún no hay capturas terminadas.")
            captures.forEachIndexed { index, capture ->
                OutlinedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Captura ${captures.size - index}", style = MaterialTheme.typography.titleMedium)
                            IconButton(onClick = { pendingDelete = capture.id }, enabled = !busy,
                                modifier = Modifier.semantics { contentDescription = "Borrar captura ${captures.size - index}" }) {
                                Text("🗑", style = MaterialTheme.typography.titleLarge)
                            }
                        }
                        Text(DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(capture.createdAt)))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            listOf("Etiqueta" to capture.label, "Producto" to capture.product, "Fachada" to capture.facade).forEach { (name, path) ->
                                Column(Modifier.weight(1f)) {
                                    PhotoPreview(path, name, Modifier.fillMaxWidth().height(96.dp))
                                    Text(name, style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                        TextButton(onClick = { onEdit(capture.id) }, enabled = !busy) { Text("Editar captura") }
                        Button(onClick = { onExport(capture) }, enabled = !busy) { Text(if (busy) "Guardando…" else "Guardar fotos en galería") }
                    }
                }
            }
        }
        }
    }
    val deleteId = pendingDelete
    if (deleteId != null) {
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("¿Seguro que quieres borrar esta captura?") },
            text = { Text("Se eliminará del historial. Las fotos guardadas en la galería permanecerán allí.") },
            confirmButton = { TextButton(onClick = { onDelete(deleteId); pendingDelete = null }) { Text("Borrar") } },
            dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("Cancelar") } }
        )
    }
}
