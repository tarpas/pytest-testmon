package sk.infinit.testmon.services.cache

import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import com.intellij.openapi.module.Module
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.getModuleRuntimeInfoFiles
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

            val moduleRuntimeInfoFiles = getModuleRuntimeInfoFiles(module)
                    ?: return null

            val fileMarks = ArrayList<PyFileMark>()

            for (moduleRuntimeInfoFile in moduleRuntimeInfoFiles) {
                val databaseService = DatabaseService(moduleRuntimeInfoFile)

                val tempFileMarks = databaseService.getPyFileMarks(fullPyFilePath, fileMarkType.value)

                for (fileMark in tempFileMarks) {
                    fileMark.exception = getPyException(fileMark.exceptionId, databaseService)
                }

                fileMarks.addAll(tempFileMarks)
            }

            this.fileMarkCacheMap[keyPair] = fileMarks

            return this.fileMarkCacheMap[keyPair]
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
     * Get [PyException] from cache by id for provided [DatabaseService] (one runtime-file).
     */
    private fun getPyException(exceptionId: Int, databaseService: DatabaseService): PyException? {
        if (this.exceptionCacheMap.containsKey(exceptionId)) {
            return this.exceptionCacheMap[exceptionId]
        }

        try {
            val exception = databaseService.getPyException(exceptionId)
                    ?: return null

            this.exceptionCacheMap[exceptionId] = exception

            return exception
        } catch (exception: Exception) {
            logErrorMessage(exception, module.project)
        }

        return null
    }
}