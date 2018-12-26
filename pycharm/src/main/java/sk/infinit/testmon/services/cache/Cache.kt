package sk.infinit.testmon.services.cache

import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.database.PyFileMark

/**
 * Runtime info cache interface.
 */
interface Cache {
    val size: Int

    fun getRedUnderlineFileMarks(fullPyFilePath: String): List<PyFileMark>?

    fun getSuffixFileMarks(fullPyFilePath: String): List<PyFileMark>?

    fun getGutterLinkFileMarks(fullPyFilePath: String): List<PyFileMark>?

    fun getException(exceptionId: Int): PyException?

    //fun remove(key: String)

    fun clear()
}