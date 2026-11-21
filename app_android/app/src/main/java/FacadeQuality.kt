package com.example.tiendas3b

import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.suspendCancellableCoroutine

/** Reviews the strongest readable text line and its surrounding area, not only the background. */
suspend fun inspectFacade(context: Context, path: String, preview: Bitmap): List<String> {
    return try {
        val image = InputImage.fromFilePath(context, Uri.fromFile(File(path)))
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val line = try {
            suspendCancellableCoroutine<FacadeText?> { continuation ->
                recognizer.process(image).addOnSuccessListener { result ->
                    val lines = result.textBlocks.flatMap { it.lines }.mapNotNull {
                        val box = it.boundingBox ?: return@mapNotNull null
                        val letters = it.text.count(Char::isLetter)
                        if (letters < 4) null else FacadeText(box.left, box.top, box.right, box.bottom, letters)
                    }
                    if (continuation.isActive) continuation.resume(lines.maxByOrNull { it.letters })
                }.addOnFailureListener {
                    if (continuation.isActive) continuation.resumeWithException(it)
                }
            }
        } finally {
            recognizer.close()
        }
        if (line == null) return listOf("No se distingue texto de la fachada. Acércate y enfoca el nombre de la tienda.")
        val rotated = image.rotationDegrees == 90 || image.rotationDegrees == 270
        val originalWidth = if (rotated) image.height else image.width
        val originalHeight = if (rotated) image.width else image.height
        val region = facadeRegion(line, originalWidth, originalHeight, preview.width, preview.height)
            ?: return listOf("El texto se ve demasiado pequeño. Acércate a la fachada.")
        val cropped = Bitmap.createBitmap(preview, region.left, region.top, region.right - region.left, region.bottom - region.top)
        try {
            val warnings = inspectImage(cropped).messages
            buildList {
                if (warnings.any { it.contains("poca luz") }) {
                    add("El área del texto está muy oscura. Busca más luz y vuelve a tomar la foto.")
                }
                if (warnings.any { it.contains("borrosa") }) {
                    add("El texto de la fachada puede estar borroso. Mantén el teléfono quieto y vuelve a tomar la foto.")
                }
            }
        } finally {
            if (cropped !== preview) cropped.recycle()
        }
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        listOf("No se pudo revisar la fachada. Vuelve a tomar la foto.")
    }
}

internal data class FacadeText(val left: Int, val top: Int, val right: Int, val bottom: Int, val letters: Int)
internal data class FacadeRegion(val left: Int, val top: Int, val right: Int, val bottom: Int)

internal fun facadeRegion(line: FacadeText, originalWidth: Int, originalHeight: Int, width: Int, height: Int): FacadeRegion? {
    if (originalWidth <= 0 || originalHeight <= 0 || width < 12 || height < 12) return null
    val left = (line.left.toLong() * width / originalWidth).toInt().coerceIn(0, width)
    val right = (line.right.toLong() * width / originalWidth).toInt().coerceIn(0, width)
    val top = (line.top.toLong() * height / originalHeight).toInt().coerceIn(0, height)
    val bottom = (line.bottom.toLong() * height / originalHeight).toInt().coerceIn(0, height)
    if (right - left < 12 || bottom - top < 12) return null
    return FacadeRegion(left, top, right, bottom)
}
