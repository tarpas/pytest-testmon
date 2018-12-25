package sk.infinit.testmon.services.cache

import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.extensions.FileMarkProvider
import com.intellij.openapi.module.Module
import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.getDatabaseServiceProjectComponent

/**
 * Service implementation of [Cache].
 */
class CacheService(private val module: Module) : Cache {

    private val fileMarkCacheMap = HashMap<String, List<PyFileMark>>()

    private val exceptionCacheMap = HashMap<Int, PyException>()

    override val size: Int
        get() = fileMarkCacheMap.size

    /**
     * Get [List<PyFileMark] from cache.
     */
    override fun getRedUnderlineDecorationFileMarks(fullPyFilePath: String): List<PyFileMark>? {
        if (this.fileMarkCacheMap.containsKey(fullPyFilePath)) {
            return this.fileMarkCacheMap[fullPyFilePath]
        }

        val psiElementErrorProvider = FileMarkProvider(getDatabaseServiceProjectComponent(module.project))

        val fileMarks = psiElementErrorProvider.getPyFileMarks(fullPyFilePath, FileMarkType.RED_UNDERLINE_DECORATION)

        this.fileMarkCacheMap[fullPyFilePath] = fileMarks

        return fileMarks
    }

    /**
     * Get [PyException] from cache by id.
     */
    override fun getException(exceptionId: Int): PyException? {
        if (this.exceptionCacheMap.containsKey(exceptionId)) {
            return this.exceptionCacheMap[exceptionId]
        }

        val exception = getFileMarkProvider().getException(exceptionId)
                ?: return null

        this.exceptionCacheMap[exceptionId] = exception

        return exception
    }

    /**
     * Remove from [fileMarkCacheMap].
     */
    /*override fun remove(key: String) {
        this.fileMarkCacheMap.remove(key)
    }*/

    /**
     * Clear cache's.
     */
    override fun clear() {
        this.fileMarkCacheMap.clear()
        this.exceptionCacheMap.clear()
    }

    /**
     * Get [FileMarkProvider] instance using [getDatabaseServiceProjectComponent] method.
     */
    private fun getFileMarkProvider() = FileMarkProvider(getDatabaseServiceProjectComponent(module.project))
}