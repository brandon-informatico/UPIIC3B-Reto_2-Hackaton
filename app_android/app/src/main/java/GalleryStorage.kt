package com.example.tiendas3b

import android.content.ContentValues
import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.util.UUID

data class SavedCapture(val id: String, val createdAt: Long, val label: String, val product: String, val facade: String)

class GalleryStorage(private val context: Context) {
    private val prefs = context.getSharedPreferences("gallery_exports", Context.MODE_PRIVATE)

    /** Reusing a facade reuses its gallery entry too. Safe to retry after a partial failure. */
    fun save(capture: SavedCapture) {
        listOf("etiqueta" to capture.label, "producto" to capture.product, "fachada" to capture.facade)
            .forEach { (type, path) -> saveOne(type, path) }
    }

    private fun saveOne(type: String, path: String) {
        val existing = prefs.getString(path, null)
        if (existing != null) {
            val exists = try {
                context.contentResolver.openFileDescriptor(Uri.parse(existing), "r")?.use { true } ?: false
            } catch (_: Exception) { false }
            if (exists) return
        }
        val file = File(path)
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, options)
        val mime = options.outMimeType ?: throw java.io.IOException("Imagen no válida")
        val suffix = when (mime) { "image/jpeg" -> "jpg"; "image/png" -> "png"; "image/webp" -> "webp"; else -> throw java.io.IOException("Formato no compatible") }
        val name = "3B_${type}_${UUID.randomUUID()}.$suffix"
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, mime)
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/Tiendas3B")
                put(MediaStore.Images.Media.IS_PENDING, 1)
            } else {
                @Suppress("DEPRECATION")
                val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), "Tiendas3B")
                if (!dir.exists() && !dir.mkdirs()) throw java.io.IOException("No se pudo crear la carpeta")
                @Suppress("DEPRECATION")
                put(MediaStore.Images.Media.DATA, File(dir, name).absolutePath)
            }
        }
        val uri = context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
            ?: throw java.io.IOException("No se pudo crear la imagen")
        try {
            context.contentResolver.openOutputStream(uri)?.use { output ->
                file.inputStream().use { it.copyTo(output) }
            } ?: throw java.io.IOException("No se pudo guardar la imagen")
            if (Build.VERSION.SDK_INT >= 29) {
                val ready = ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }
                if (context.contentResolver.update(uri, ready, null, null) != 1) throw java.io.IOException()
            }
            if (!prefs.edit().putString(path, uri.toString()).commit()) throw java.io.IOException()
        } catch (e: Exception) {
            context.contentResolver.delete(uri, null, null)
            throw e
        }
    }
}
