package sk.infinit.testmon.services.cache

import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import com.intellij.openapi.module.Module
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.getModuleRuntimeInfoFile
import sk.infinit.testmon.logErrorMessage

/**
 * Service implementation of [Cache].
 */
class CacheService(private val module: Module) : Cache {

    private val fileMarkCacheMap = HashMap<Pair<String, FileMarkType>, List<PyFileMark>>()

    private val exceptionCacheMap = HashMap<Int, PyException>()

    override fun getPyFileMarks(fullPyFilePath: String, fileMarkType: FileMarkType): List<PyFileMark>? {
        try {
            val keyPair = Pair(fullPyFilePath, fileMarkType)

            if (this.fileMarkCacheMap.containsKey(keyPair)) {
                return this.fileMarkCacheMap[keyPair]
            }

            val fileMarkProvider = getDatabaseService() ?: return null

            this.fileMarkCacheMap[keyPair] = fileMarkProvider.getPyFileMarks(fullPyFilePath, fileMarkType.value)

            return this.fileMarkCacheMap[keyPair]
        } catch (exception: Exception) {
            logErrorMessage(exception, module.project)
        }

        return null
    }

    /**
     * Get [PyException] from cache by id.
     */
    override fun getPyException(exceptionId: Int): PyException? {
        if (this.exceptionCacheMap.containsKey(exceptionId)) {
            return this.exceptionCacheMap[exceptionId]
        }

        try {
            val fileMarkProvider = getDatabaseService() ?: return null

            val exception = fileMarkProvider.getPyException(exceptionId)
                    ?: return null

            this.exceptionCacheMap[exceptionId] = exception

            return exception
        } catch (exception: Exception) {
            logErrorMessage(exception, module.project)
        }

        return null
    }

    /**
     * Clear cache's.
     */
    override fun clear() {
        this.fileMarkCacheMap.clear()
        this.exceptionCacheMap.clear()
    }

    /**
     * Get [FileMarkProvider] instance from [module] data.
     */
    private fun getDatabaseService(): DatabaseService? {
        val moduleRuntimeInfoFile = getModuleRuntimeInfoFile(module)
                ?: return null

        return DatabaseService(moduleRuntimeInfoFile)
    }
}