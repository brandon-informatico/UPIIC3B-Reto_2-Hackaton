package com.example.tiendas3b

import android.os.Bundle
import android.os.Build
import android.Manifest
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.result.PickVisualMediaRequest
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.TextButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.tiendas3b.ui.theme.Tiendas3BTheme
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { Tiendas3BTheme { CaptureHome() } }
    }
}

enum class PhotoType(val title: String, val guidance: String) {
    LABEL("Etiqueta de precio", "Acércate y muestra el precio y el código completos."),
    PRODUCT("Producto", "Muestra el producto completo, su nombre y presentación."),
    STORE("Fachada", "Encuadra la fachada y el nombre de la tienda.")
}

@Composable
private fun CaptureHome() {
    val context = LocalContext.current
    val storage = remember { CaptureStorage(context) }
    val scope = rememberCoroutineScope()
    var revision by remember { mutableIntStateOf(0) }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var importedPath by rememberSaveable { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var importing by remember { mutableStateOf(false) }
    var showingHistory by rememberSaveable { mutableStateOf(false) }
    var editingId by rememberSaveable { mutableStateOf<String?>(null) }
    var showingFacade by remember { mutableStateOf(false) }
    var pendingExport by remember { mutableStateOf<SavedCapture?>(null) }
    var permissionDialog by remember { mutableStateOf(false) }
    var settingsDialog by remember { mutableStateOf(false) }
    fun export(capture: SavedCapture) {
        importing = true
        scope.launch {
            val succeeded = withContext(Dispatchers.IO) {
                try { GalleryStorage(context).save(capture); true } catch (_: Exception) { false }
            }
            importing = false
            message = if (succeeded) "Fotos guardadas en la galería, en Tiendas3B."
                else "No se pudieron guardar todas las fotos en la galería. Puedes reintentarlo desde el historial."
        }
    }
    val storagePermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val capture = pendingExport
        pendingExport = null
        if (granted && capture != null) export(capture)
        else {
            message = "La captura está guardada en la app, pero no en la galería."
            if ((context as? ComponentActivity)?.shouldShowRequestPermissionRationale(Manifest.permission.WRITE_EXTERNAL_STORAGE) == false) settingsDialog = true
        }
    }
    fun requestExport(capture: SavedCapture) {
        if (Build.VERSION.SDK_INT < 29 && ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            pendingExport = capture
            permissionDialog = true
        } else export(capture)
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            importing = true
            scope.launch {
                val path = withContext(Dispatchers.IO) {
                    var file: File? = null
                    try {
                        val dir = File(context.filesDir, "photos")
                        if (!dir.exists() && !dir.mkdirs()) throw java.io.IOException()
                        file = File.createTempFile("facade_", ".image", dir)
                        val input = context.contentResolver.openInputStream(uri) ?: throw java.io.IOException()
                        input.use { source -> file.outputStream().use { source.copyTo(it) } }
                        file.absolutePath
                    } catch (_: Exception) {
                        file?.delete()
                        null
                    }
                }
                importing = false
                if (path == null) message = "No se pudo abrir la imagen. Elige otra foto."
                else {
                    importedPath = path
                    selected = PhotoType.STORE.name
                    message = null
                }
            }
        }
    }
    val photo = PhotoType.entries.firstOrNull { it.name == selected }
    val editId = editingId
    if (photo != null) {
        CameraScreen(photo = photo, initialPath = importedPath, onSave = if (editId != null) { path: String ->
            if (storage.replacePhoto(editId, photo, path)) {
                revision++
                message = "Foto actualizada. Guardando una copia en la galería…"
                storage.history().firstOrNull { it.id == editId }?.let { requestExport(it) }
                true
            } else false
        } else null, onClose = {
            selected = null
            importedPath = null
            revision++
        })
    } else if (editId != null) {
        val capture = remember(revision, editId) { storage.history().firstOrNull { it.id == editId } }
        if (capture != null) {
            EditCaptureScreen(capture, onBack = { editingId = null; message = null }, onChange = {
                importedPath = null
                selected = it.name
            }, onPickFacade = {
                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }, busy = importing, message = message)
        } else {
            androidx.compose.runtime.LaunchedEffect(editId) {
                editingId = null
                message = "No se encontró la captura."
            }
        }
    } else if (showingHistory) {
        val captures = remember(revision) { storage.history() }
        HistoryScreen(captures, onBack = { showingHistory = false; message = null }, onExport = { requestExport(it) }, onDelete = { id ->
            if (storage.delete(id)) { revision++; message = "Captura eliminada del historial." }
            else message = "No se pudo borrar la captura. Inténtalo de nuevo."
        }, onEdit = { editingId = it; message = null }, message = message, busy = importing)
    } else {
        val current = remember(revision) { PhotoType.entries.associateWith { storage.current(it) } }
        val next = PhotoType.entries.firstOrNull { current[it] == null }
        val count = remember(revision) { storage.completedCount() }
        val lastFacade = remember(revision) { storage.lastFacade() }
        Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            Image(
                painter = painterResource(R.drawable.fondo_app),
                contentDescription = null,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit,
                alpha = 0.12f
            )
            Scaffold(modifier = Modifier.fillMaxSize(), containerColor = Color.Transparent) { innerPadding ->
            Column(
                modifier = Modifier.fillMaxSize().padding(innerPadding)
                    .verticalScroll(rememberScrollState()).padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text("Captura de precios", style = MaterialTheme.typography.headlineMedium)
                Text(if (next == null) "Las tres fotos están listas. Guarda la captura para continuar."
                    else "Siguiente paso: ${next.title.lowercase()}.")
                Text("Capturas guardadas: $count", style = MaterialTheme.typography.bodyMedium)
                OutlinedButton(onClick = { showingHistory = true; message = null }, enabled = !importing) { Text("Ver historial") }
                message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                PhotoType.entries.forEachIndexed { index, type ->
                    val saved = current[type] != null
                    OutlinedCard(modifier = Modifier.fillMaxWidth()) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text("${index + 1}. ${type.title}", style = MaterialTheme.typography.titleMedium)
                            Text(
                                text = if (saved) "✓ Guardada" else if (type == next) "Pendiente · Siguiente paso" else "Pendiente",
                                color = if (saved) Color(0xFF1B6B37) else Color(0xFF9A4D00),
                                style = MaterialTheme.typography.labelLarge
                            )
                            Text(type.guidance, style = MaterialTheme.typography.bodyMedium)
                            Button(onClick = {
                                importedPath = null
                                selected = type.name
                            }, enabled = !importing) { Text(if (saved) "Cambiar foto" else "Tomar foto") }
                            if (type == PhotoType.STORE) {
                                if (lastFacade != null) {
                                    OutlinedButton(onClick = { showingFacade = true }, enabled = !importing) {
                                        Text("Ver fachada anterior")
                                    }
                                }
                                OutlinedButton(onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, enabled = !importing) {
                                    Text(if (importing) "Abriendo foto…" else "Elegir foto de fachada")
                                }
                            }
                        }
                    }
                }
                Button(
                    onClick = {
                        if (storage.complete()) {
                            revision++
                            message = "Captura guardada. Guardando fotos en la galería…"
                            storage.history().firstOrNull()?.let { requestExport(it) }
                        } else message = "No se pudo guardar la captura. Comprueba las tres fotos e inténtalo de nuevo."
                    },
                    enabled = next == null && !importing,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Guardar captura y comenzar otra") }
            }
            }
        }
    }
    if (showingFacade) {
        val path = storage.lastFacade()
        AlertDialog(
            onDismissRequest = { showingFacade = false },
            title = { Text("¿Usar esta fachada?") },
            text = {
                Column {
                    Text("Confirma que corresponde a esta tienda.")
                    if (path != null) PhotoPreview(path, "Fachada anterior", Modifier.fillMaxWidth().height(220.dp))
                    else Text("La foto ya no está disponible.")
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    if (storage.reuseFacade()) { revision++; message = null }
                    else message = "No se pudo reutilizar la fachada."
                    showingFacade = false
                }, enabled = path != null) { Text("Sí, usar foto") }
            },
            dismissButton = { TextButton(onClick = { showingFacade = false }) { Text("Cancelar") } }
        )
    }
    if (settingsDialog) {
        AlertDialog(
            onDismissRequest = { settingsDialog = false },
            title = { Text("Permiso de almacenamiento") },
            text = { Text("Puedes habilitar el almacenamiento en ajustes y después reintentar desde el historial.") },
            confirmButton = { TextButton(onClick = {
                settingsDialog = false
                context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null)))
            }) { Text("Abrir ajustes") } },
            dismissButton = { TextButton(onClick = { settingsDialog = false }) { Text("Cerrar") } }
        )
    }
    if (permissionDialog) {
        AlertDialog(
            onDismissRequest = { permissionDialog = false; pendingExport = null },
            title = { Text("Guardar fotos en la galería") },
            text = { Text("En esta versión de Android se necesita acceso al almacenamiento para guardar las fotos en la galería.") },
            confirmButton = { TextButton(onClick = { permissionDialog = false; storagePermission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE) }) { Text("Continuar") } },
            dismissButton = { TextButton(onClick = { permissionDialog = false; pendingExport = null }) { Text("Ahora no") } }
        )
    }
}
