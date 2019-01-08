package sk.infinit.testmon.services.cache

import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark

/**
 * Runtime info cache interface.
 */
interface Cache {
    fun getPyFileMarks(fullPyFilePath: String, fileMarkType: FileMarkType): List<PyFileMark>?

    fun clear()
}