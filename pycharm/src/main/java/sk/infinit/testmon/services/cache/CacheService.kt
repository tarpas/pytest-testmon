package sk.infinit.testmon.services.cache

import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.extensions.FileMarkProvider
import com.intellij.openapi.module.Module
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.getModuleRuntimeInfoFile
import sk.infinit.testmon.logErrorMessage

/**
 * Service implementation of [Cache].
 */
class CacheService(private val module: Module) : Cache {

    private val redUnderlineFileMarkCacheMap = HashMap<String, List<PyFileMark>>()

    private val suffixFileMarkCacheMap = HashMap<String, List<PyFileMark>>()

    private val gutterLinkFileMarkCacheMap = HashMap<String, List<PyFileMark>>()

    private val exceptionCacheMap = HashMap<Int, PyException>()

    override val size: Int
        get() = redUnderlineFileMarkCacheMap.size

    /**
     * Get [List<PyFileMark] from cache.
     */
    override fun getRedUnderlineFileMarks(fullPyFilePath: String): List<PyFileMark>? {
        if (this.redUnderlineFileMarkCacheMap.containsKey(fullPyFilePath)) {
            return this.redUnderlineFileMarkCacheMap[fullPyFilePath]
        }

        try {
            val fileMarkProvider = getFileMarkProvider() ?: return null

            val fileMarks = fileMarkProvider.getPyFileMarks(fullPyFilePath, FileMarkType.RED_UNDERLINE_DECORATION)

            this.redUnderlineFileMarkCacheMap[fullPyFilePath] = fileMarks

            return fileMarks
        } catch (exception: Exception) {
            logErrorMessage(exception, module.project)
        }

        return null
    }

    override fun getSuffixFileMarks(fullPyFilePath: String): List<PyFileMark>? {
        if (suffixFileMarkCacheMap.containsKey(fullPyFilePath)) {
            return suffixFileMarkCacheMap[fullPyFilePath]
        }

        try {
            val fileMarkProvider = getFileMarkProvider() ?: return null

            val fileMarks = fileMarkProvider.getPyFileMarks(fullPyFilePath, FileMarkType.SUFFIX)

            this.suffixFileMarkCacheMap[fullPyFilePath] = fileMarks

            return fileMarks
        } catch (exception: Exception) {
            logErrorMessage(exception, module.project)
        }

        return null
    }

    override fun getGutterLinkFileMarks(fullPyFilePath: String): List<PyFileMark>? {
        if (gutterLinkFileMarkCacheMap.containsKey(fullPyFilePath)) {
            return gutterLinkFileMarkCacheMap[fullPyFilePath]
        }

        try {
            val fileMarkProvider = getFileMarkProvider() ?: return null

            val fileMarks = fileMarkProvider.getPyFileMarks(fullPyFilePath, FileMarkType.GUTTER_LINK)

            this.gutterLinkFileMarkCacheMap[fullPyFilePath] = fileMarks

            return fileMarks
        } catch (exception: Exception) {
            logErrorMessage(exception, module.project)
        }

        return null
    }

    /**
     * Get [PyException] from cache by id.
     */
    override fun getException(exceptionId: Int): PyException? {
        if (this.exceptionCacheMap.containsKey(exceptionId)) {
            return this.exceptionCacheMap[exceptionId]
        }

        try {
            val fileMarkProvider = getFileMarkProvider() ?: return null

            val exception = fileMarkProvider.getException(exceptionId)
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
        this.redUnderlineFileMarkCacheMap.clear()
        this.suffixFileMarkCacheMap.clear()
        this.gutterLinkFileMarkCacheMap.clear()
        this.exceptionCacheMap.clear()
    }

    /**
     * Get [FileMarkProvider] instance from [module] data.
     */
    private fun getFileMarkProvider(): FileMarkProvider? {
        val moduleRuntimeInfoFile = getModuleRuntimeInfoFile(module) ?: return null

        return FileMarkProvider(DatabaseService(moduleRuntimeInfoFile))
    }
}