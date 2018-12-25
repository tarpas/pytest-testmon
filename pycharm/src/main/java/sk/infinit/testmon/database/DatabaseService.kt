package sk.infinit.testmon.database

/**
 * Database service interface for runtime-info.
 */
interface DatabaseService {

    /**
     * Get PyFileMark's list for PyException.
     *
     * @return List<PyFileMark>
     */
    fun getFileMarks(fileName: String, type: String): List<PyFileMark>

    /**
     * Get PyException object by id.
     */
    fun getPyException(exceptionId: Int): PyException?
}