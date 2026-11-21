package com.example.tiendas3b

import android.graphics.Bitmap
import kotlin.math.max
import kotlin.math.roundToInt

/** Heuristic checks only: passing does not establish subject identity or text readability. */
data class QualityResult(val messages: List<String>)

fun inspectImage(bitmap: Bitmap): QualityResult {
    val scale = minOf(1f, 640f / max(bitmap.width, bitmap.height))
    val width = max(1, (bitmap.width * scale).roundToInt())
    val height = max(1, (bitmap.height * scale).roundToInt())
    val scaled = if (scale < 1f) Bitmap.createScaledBitmap(bitmap, width, height, true) else bitmap
    return try {
        val pixels = IntArray(width * height)
        scaled.getPixels(pixels, 0, width, 0, 0, width, height)
        val luminance = IntArray(pixels.size) { i ->
            val p = pixels[i]
            (77 * (p shr 16 and 255) + 150 * (p shr 8 and 255) + 29 * (p and 255)) shr 8
        }
        assessLuminance(luminance, width, height)
    } finally {
        if (scaled !== bitmap) scaled.recycle()
    }
}

internal fun assessLuminance(values: IntArray, width: Int, height: Int): QualityResult {
    if (width < 12 || height < 12 || values.size != width * height) {
        return QualityResult(listOf("No se pudo evaluar la foto. Intenta tomarla de nuevo."))
    }
    // Inspect the central region where the user is asked to place the subject.
    val left = width / 4
    val right = width - left
    val top = height / 4
    val bottom = height - top
    var dark = 0
    var bright = 0
    var total = 0
    var sum = 0.0
    var squares = 0.0
    for (y in top + 1 until bottom - 1) {
        for (x in left + 1 until right - 1) {
            val i = y * width + x
            val value = values[i]
            if (value < 35) dark++
            if (value > 245) bright++
            total++
            // Compare local averages rather than single pixels to reduce sensor noise.
            val leftMean = (values[i - width - 1] + values[i - 1] + values[i + width - 1]) / 3.0
            val rightMean = (values[i - width + 1] + values[i + 1] + values[i + width + 1]) / 3.0
            val topMean = (values[i - width - 1] + values[i - width] + values[i - width + 1]) / 3.0
            val bottomMean = (values[i + width - 1] + values[i + width] + values[i + width + 1]) / 3.0
            val gradient = (rightMean - leftMean) * (rightMean - leftMean) +
                (bottomMean - topMean) * (bottomMean - topMean)
            sum += gradient
            squares += value
        }
    }
    val messages = mutableListOf<String>()
    if (dark.toDouble() / total > 0.45 || squares / total < 45) {
        messages.add("Hay poca luz en el centro. Busca más iluminación.")
    }
    if (bright.toDouble() / total > 0.45) {
        messages.add("Hay demasiada luz en el centro. Evita reflejos.")
    }
    if (sum / total < 60.0) {
        messages.add("La imagen puede estar borrosa o tener poco detalle. Acércate y mantén el teléfono quieto.")
    }
    return QualityResult(messages)
}
