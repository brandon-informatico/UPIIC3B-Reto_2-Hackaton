package com.example.tiendas3b

import android.content.Context
import android.net.Uri
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

/** Reading text is a necessary check, not proof that a price or product is correct. */
suspend fun inspectText(context: Context, path: String, photo: PhotoType): List<String> {
    return try {
        val image = InputImage.fromFilePath(context, Uri.fromFile(java.io.File(path)))
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        try {
            suspendCancellableCoroutine { continuation ->
                recognizer.process(image).addOnSuccessListener { result ->
                    if (continuation.isActive) continuation.resume(textWarnings(photo, result.text))
                }.addOnFailureListener {
                    if (continuation.isActive) continuation.resume(listOf("No se pudo revisar el texto. Vuelve a tomar la foto."))
                }
            }
        } finally {
            recognizer.close()
        }
    } catch (cancelled: kotlinx.coroutines.CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        listOf("No se pudo revisar el texto. Vuelve a tomar la foto.")
    }
}

internal fun textWarnings(photo: PhotoType, text: String): List<String> {
    val hasWords = text.count { it.isLetter() } >= 3
    return when (photo) {
        PhotoType.LABEL -> buildList {
            if (!hasWords) add("No se distingue la descripción. Acércate a la etiqueta y enfoca.")
            if (!Regex("""(?<!\d)\d{1,4}([.,]\d{1,2})?(?!\d)""").containsMatchIn(text)) {
                add("No se pudo leer un posible precio. Acércate y evita reflejos.")
            }
        }
        PhotoType.PRODUCT -> if (!hasWords) listOf("No se distingue texto del producto. Acércate y enfoca su frente.") else emptyList()
        PhotoType.STORE -> if (!hasWords) listOf("No se distingue el nombre de la tienda. Acércate o cambia el ángulo.") else emptyList()
    }
}
