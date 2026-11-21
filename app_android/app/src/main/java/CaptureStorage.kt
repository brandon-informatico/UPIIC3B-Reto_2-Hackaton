package com.example.tiendas3b

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/** Stores image paths together; existing captures retain their own photo references. */
class CaptureStorage(context: Context) {
    private val prefs = context.getSharedPreferences("photos", Context.MODE_PRIVATE)
    private val contextFilesDir = context.filesDir

    fun current(type: PhotoType): String? = prefs.getString(type.name, null)?.takeIf { File(it).isFile }
    fun lastFacade(): String? = prefs.getString("last_facade", null)?.takeIf { File(it).isFile }

    fun reuseFacade(): Boolean {
        val path = lastFacade() ?: return false
        return prefs.edit().putString(PhotoType.STORE.name, path).commit()
    }

    fun complete(): Boolean {
        val label = current(PhotoType.LABEL) ?: return false
        val product = current(PhotoType.PRODUCT) ?: return false
        val facade = current(PhotoType.STORE) ?: return false
        return try {
            val captures = JSONArray(prefs.getString("completed_captures", "[]"))
            captures.put(JSONObject()
                .put("id", UUID.randomUUID().toString())
                .put("createdAt", System.currentTimeMillis())
                .put("label", label)
                .put("product", product)
                .put("facade", facade))
            prefs.edit()
                .putString("completed_captures", captures.toString())
                .putString("last_facade", facade)
                .remove(PhotoType.LABEL.name)
                .remove(PhotoType.PRODUCT.name)
                .remove(PhotoType.STORE.name)
                .commit()
        } catch (_: Exception) {
            false
        }
    }

    fun history(): List<SavedCapture> = try {
        val array = JSONArray(prefs.getString("completed_captures", "[]"))
        (0 until array.length()).map { array.getJSONObject(it) }.map {
            SavedCapture(it.getString("id"), it.optLong("createdAt"), it.getString("label"),
                it.getString("product"), it.getString("facade"))
        }.asReversed()
    } catch (_: Exception) { emptyList() }

    /** Replaces only the selected image in the selected capture, preserving other references. */
    fun replacePhoto(id: String, type: PhotoType, path: String): Boolean {
        if (!File(path).isFile) return false
        return try {
            val captures = JSONArray(prefs.getString("completed_captures", "[]"))
            var found = false
            val field = when (type) {
                PhotoType.LABEL -> "label"
                PhotoType.PRODUCT -> "product"
                PhotoType.STORE -> "facade"
            }
            for (i in 0 until captures.length()) {
                val item = captures.getJSONObject(i)
                if (item.getString("id") == id) {
                    item.put(field, path)
                    found = true
                    break
                }
            }
            found && prefs.edit().putString("completed_captures", captures.toString()).commit()
        } catch (_: Exception) { false }
    }

    /** Removes a history entry, retaining files referenced by another capture or the active draft. */
    fun delete(id: String): Boolean {
        return try {
        val captures = JSONArray(prefs.getString("completed_captures", "[]"))
        val remaining = JSONArray()
        var removed: JSONObject? = null
        for (i in 0 until captures.length()) {
            val item = captures.getJSONObject(i)
            if (item.getString("id") == id) removed = item else remaining.put(item)
        }
        val deleted = removed ?: return false
        val references = mutableSetOf<String>()
        for (i in 0 until remaining.length()) {
            val item = remaining.getJSONObject(i)
            listOf("label", "product", "facade").forEach { references.add(item.getString(it)) }
        }
        PhotoType.entries.mapNotNullTo(references) { current(it) }
        val last = prefs.getString("last_facade", null)
        val edit = prefs.edit().putString("completed_captures", remaining.toString())
        if (last == deleted.optString("facade") && last !in references) {
            if (remaining.length() > 0) edit.putString("last_facade", remaining.getJSONObject(remaining.length() - 1).getString("facade"))
            else edit.remove("last_facade")
        } else if (last != null) {
            references.add(last)
        }
        if (!edit.commit()) return false
        val photosRoot = File(contextFilesDir, "photos").canonicalFile
        listOf("label", "product", "facade").map { deleted.getString(it) }.distinct()
            .filterNot { it in references }
            .forEach { path ->
                try {
                    val file = File(path).canonicalFile
                    if (file.parentFile == photosRoot) file.delete()
                } catch (_: Exception) { /* History is already saved; leave the file untouched. */ }
            }
        true
        } catch (_: Exception) { false }
    }

    fun completedCount(): Int = try {
        JSONArray(prefs.getString("completed_captures", "[]")).length()
    } catch (_: Exception) { 0 }
}
