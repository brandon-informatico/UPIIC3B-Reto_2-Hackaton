package com.example.tiendas3b

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun CameraScreen(photo: PhotoType, initialPath: String? = null, onSave: ((String) -> Boolean)? = null, onClose: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    var imagePath by rememberSaveable(photo, initialPath) { mutableStateOf(initialPath) }
    var error by remember { mutableStateOf<String?>(null) }
    var taking by remember { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        granted = it
        if (!it) error = "Necesitamos acceso a la cámara para tomar fotos. Puedes habilitarlo en los ajustes de la aplicación."
    }
    val controller = remember {
        LifecycleCameraController(context).apply { cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA }
    }
    fun close() {
        imagePath?.let { File(it).delete() }
        onClose()
    }
    BackHandler { close() }

    DisposableEffect(granted, lifecycleOwner, imagePath) {
        if (granted && imagePath == null) {
            try {
                controller.bindToLifecycle(lifecycleOwner)
            } catch (exception: Exception) {
                error = "No se pudo iniciar la cámara. Comprueba que el dispositivo tenga cámara disponible."
            }
        }
        onDispose { controller.unbind() }
    }

    Scaffold { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(photo.title, style = MaterialTheme.typography.headlineSmall)
            Text(photo.guidance)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

            val captured = imagePath
            if (captured != null) {
                val review by produceState<PhotoReview?>(initialValue = null, captured) {
                    value = withContext(Dispatchers.IO) {
                        val bitmap = loadPreview(captured)
                        if (bitmap == null) PhotoReview(null, null)
                        else {
                            val contentWarnings = when (photo) {
                                PhotoType.PRODUCT -> inspectProduct(context, captured)
                                PhotoType.STORE -> inspectFacade(context, captured, bitmap)
                                PhotoType.LABEL -> inspectText(context, captured, photo)
                            }
                            val warnings = inspectImage(bitmap).messages + contentWarnings
                            PhotoReview(bitmap, QualityResult(warnings))
                        }
                    }
                }
                val bitmap = review?.bitmap
                if (bitmap != null) {
                    Image(
                        bitmap = bitmap.asImageBitmap(),
                        contentDescription = "Vista previa de la foto",
                        modifier = Modifier.fillMaxWidth().weight(1f).border(
                            4.dp,
                            if (review?.quality?.messages?.isEmpty() == true) Color(0xFF218344) else MaterialTheme.colorScheme.error
                        )
                    )
                } else {
                    Text(
                        if (review == null) "Revisando foto…" else "No se pudo abrir la foto. Vuelve a tomarla.",
                        modifier = Modifier.weight(1f)
                    )
                }
                val quality = review?.quality
                if (quality != null) {
                    if (quality.messages.isEmpty()) {
                        Text("Sin alertas detectadas. Comprueba que el contenido corresponda y sea legible.", color = Color(0xFF218344))
                    } else {
                        Text("Foto no válida. Repite la toma:", color = MaterialTheme.colorScheme.error)
                        quality.messages.forEach { Text(it, color = MaterialTheme.colorScheme.error) }
                    }
                }
                Button(onClick = {
                    val prefs = context.getSharedPreferences("photos", android.content.Context.MODE_PRIVATE)
                    val saved = onSave?.invoke(captured) ?: prefs.edit().putString(photo.name, captured).commit()
                    if (saved) {
                        imagePath = null
                        onClose()
                    } else {
                        error = "No se pudo guardar la foto. Inténtalo de nuevo."
                    }
                }, enabled = bitmap != null && quality != null && quality.messages.isEmpty(), modifier = Modifier.fillMaxWidth()) {
                    Text("Guardar foto")
                }
                TextButton(onClick = {
                    File(captured).delete()
                    imagePath = null
                    error = null
                }, modifier = Modifier.fillMaxWidth()) { Text("Repetir foto") }
            } else if (!granted) {
                Text("Autoriza el uso de la cámara para continuar.")
                Button(onClick = { permission.launch(Manifest.permission.CAMERA) }) { Text("Permitir cámara") }
            } else {
                AndroidView(
                    factory = { PreviewView(it).apply { this.controller = controller } },
                    modifier = Modifier.fillMaxWidth().weight(1f)
                )
                Button(
                    onClick = {
                        val directory = File(context.filesDir, "photos")
                        if (!directory.exists() && !directory.mkdirs()) {
                            error = "No se pudo preparar el almacenamiento."
                        } else {
                            val file = File.createTempFile("capture_", ".jpg", directory)
                            taking = true
                            error = null
                            controller.takePicture(
                                ImageCapture.OutputFileOptions.Builder(file).build(),
                                ContextCompat.getMainExecutor(context),
                                object : ImageCapture.OnImageSavedCallback {
                                    override fun onImageSaved(result: ImageCapture.OutputFileResults) {
                                        taking = false
                                        imagePath = file.absolutePath
                                    }
                                    override fun onError(exception: ImageCaptureException) {
                                        taking = false
                                        file.delete()
                                        error = "No se pudo tomar la foto. Inténtalo de nuevo."
                                    }
                                }
                            )
                        }
                    },
                    enabled = !taking,
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (taking) "Tomando foto…" else "Tomar foto") }
            }
            TextButton(onClick = { close() }, enabled = !taking) { Text("Volver") }
        }
    }
}

private data class PhotoReview(val bitmap: Bitmap?, val quality: QualityResult?)

internal fun loadPreview(path: String): Bitmap? = try {
    val options = BitmapFactory.Options().apply { inSampleSize = 4 }
    val bitmap = BitmapFactory.decodeFile(path, options) ?: return null
    val orientation = ExifInterface(path).getAttributeInt(
        ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL
    )
    val degrees = when (orientation) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90f
        ExifInterface.ORIENTATION_ROTATE_180 -> 180f
        ExifInterface.ORIENTATION_ROTATE_270 -> 270f
        else -> 0f
    }
    if (degrees == 0f) bitmap else Bitmap.createBitmap(
        bitmap, 0, 0, bitmap.width, bitmap.height, Matrix().apply { postRotate(degrees) }, true
    )
} catch (_: Exception) {
    null
}
