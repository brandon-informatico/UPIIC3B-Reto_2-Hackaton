package com.example.tiendas3b

import android.content.Context
import android.net.Uri
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.objects.ObjectDetection
import com.google.mlkit.vision.objects.defaults.ObjectDetectorOptions
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.suspendCancellableCoroutine

internal data class ImageArea(val left: Int, val top: Int, val right: Int, val bottom: Int)
internal data class ReadableText(val area: ImageArea, val letters: Int)

internal fun productWarnings(
    objects: List<ImageArea>,
    text: List<ReadableText>,
    imageWidth: Int,
    imageHeight: Int
): List<String> {
    if (imageWidth <= 0 || imageHeight <= 0) {
        return listOf("No se pudo revisar el encuadre. Repite la foto.")
    }
    val area = objects
        .filter { it.right > it.left && it.bottom > it.top }
        .maxByOrNull { (it.right - it.left).toLong() * (it.bottom - it.top) }
        ?: return listOf("No se detectó un objeto. Centra el producto completo y vuelve a intentarlo.")
    val warnings = mutableListOf<String>()
    // Permit close framing while still flagging objects that touch the image edge.
    val marginX = imageWidth * 0.005
    val marginY = imageHeight * 0.005
    if (area.left <= marginX || area.top <= marginY ||
        area.right >= imageWidth - marginX || area.bottom >= imageHeight - marginY
    ) {
        warnings.add("El producto podría estar cortado. Aléjate un poco para mostrar sus bordes.")
    }
    val areaFraction = (area.right - area.left).toDouble() * (area.bottom - area.top) /
        (imageWidth.toDouble() * imageHeight)
    if (areaFraction < 0.12) {
        warnings.add("El producto se ve pequeño. Acércate sin cortar sus bordes.")
    }
    val wordsOnProduct = text.filter { word ->
        val width = maxOf(0, minOf(word.area.right, area.right) - maxOf(word.area.left, area.left))
        val height = maxOf(0, minOf(word.area.bottom, area.bottom) - maxOf(word.area.top, area.top))
        val wordArea = (word.area.right - word.area.left).toLong() * (word.area.bottom - word.area.top)
        word.letters >= 2 && wordArea > 0 && width.toLong() * height * 10 >= wordArea * 8
    }
    if (wordsOnProduct.size < 2 || wordsOnProduct.sumOf { it.letters } < 8) {
        warnings.add("No se lee suficiente texto del producto. Muestra el frente, acércate y enfoca.")
    }
    return warnings
}

suspend fun inspectProduct(context: Context, path: String): List<String> {
    return try {
        val image = InputImage.fromFilePath(context, Uri.fromFile(File(path)))
        val options = ObjectDetectorOptions.Builder()
            .setDetectorMode(ObjectDetectorOptions.SINGLE_IMAGE_MODE)
            .enableMultipleObjects()
            .build()
        val detector = ObjectDetection.getClient(options)
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        try {
            val objects = suspendCancellableCoroutine<List<ImageArea>> { continuation ->
                detector.process(image).addOnSuccessListener { result ->
                    if (continuation.isActive) continuation.resume(result.map {
                        val b = it.boundingBox
                        ImageArea(b.left, b.top, b.right, b.bottom)
                    })
                }.addOnFailureListener {
                    if (continuation.isActive) continuation.resumeWithException(it)
                }
            }
            val text = suspendCancellableCoroutine<List<ReadableText>> { continuation ->
                recognizer.process(image).addOnSuccessListener { result ->
                    val words = result.textBlocks.flatMap { it.lines }.flatMap { it.elements }
                    if (continuation.isActive) continuation.resume(words.mapNotNull { word ->
                        word.boundingBox?.let { b ->
                            ReadableText(ImageArea(b.left, b.top, b.right, b.bottom), word.text.count { it.isLetter() })
                        }
                    })
                }.addOnFailureListener {
                    if (continuation.isActive) continuation.resumeWithException(it)
                }
            }
            val rotated = image.rotationDegrees == 90 || image.rotationDegrees == 270
            val width = if (rotated) image.height else image.width
            val height = if (rotated) image.width else image.height
            productWarnings(objects, text, width, height)
        } finally {
            detector.close()
            recognizer.close()
        }
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        listOf("No se pudo revisar el producto. Vuelve a tomar la foto.")
    }
}
