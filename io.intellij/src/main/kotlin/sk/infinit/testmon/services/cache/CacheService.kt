package sk.infinit.testmon.services.cache

import com.intellij.openapi.project.Project
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.getDatabaseFiles
import sk.infinit.testmon.getVirtualFileRelativePath
import sk.infinit.testmon.logErrorMessage

/**
 * Service implementation of [Cache].
 */
class CacheService(private val project: Project) : Cache {

    private val fileMarkCacheMap = HashMap<Pair<String, FileMarkType>, List<PyFileMark>>()

    private val exceptionCacheMap = HashMap<Int, PyException>()

    override fun getPyFileMarks(absolutePyFilePath: String, fileMarkType: FileMarkType): List<PyFileMark>? {
        try {
            val keyPair = Pair(absolutePyFilePath, fileMarkType)

            if (this.fileMarkCacheMap.containsKey(keyPair)) {
                return this.fileMarkCacheMap[keyPair]
            }

            val databaseFiles = getDatabaseFiles(project)
                    ?: return null

            val fileMarks = ArrayList<PyFileMark>()

            for (databaseFile in databaseFiles) {
                val databaseService = DatabaseService(databaseFile)
                val fileRootDirectoryPath = databaseService.getDatabaseDirectory()
                val virtualFileRelativePath = getVirtualFileRelativePath(fileRootDirectoryPath, absolutePyFilePath)

                val tempFileMarks = databaseService.getPyFileMarks(virtualFileRelativePath, fileMarkType.value)

                for (fileMark in tempFileMarks) {
                    fileMark.exception = getPyException(fileMark.exceptionId, databaseService)
                    fileMark.dbDir = fileRootDirectoryPath
                }

                fileMarks.addAll(tempFileMarks)
            }

            this.fileMarkCacheMap[keyPair] = fileMarks

            return this.fileMarkCacheMap[keyPair]
        } catch (exception: Exception) {
            logErrorMessage(exception, project)
        }

        return null
    }

    override fun clear() {
        this.fileMarkCacheMap.clear()
        this.exceptionCacheMap.clear()
    }

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
            logErrorMessage(exception, project)
        }

        return null
    }

    override fun setPyFileMarksCache(keyPair : Pair<String, FileMarkType>, fileMarks : List<PyFileMark>) {
        this.fileMarkCacheMap[keyPair] = fileMarks
    }

    override fun setPyExceptionCache(key : Int, pyException : PyException) {
        this.exceptionCacheMap[key] = pyException
    }
}