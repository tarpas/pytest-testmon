package sk.infinit.testmon.extensions

import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyException
import sk.infinit.testmon.database.PyFileMark
import java.util.*
import java.util.stream.Collectors

/**
 * File mark provider. Middle layer between database API and IntelliJ UI extensions.
 */
class FileMarkProvider(private val databaseService: DatabaseService) {

    /**
     * Get PyFileMark's by py file full path.
     */
    fun getPyFileMarks(pyFileFullPath: String, fileMarkType: FileMarkType): List<PyFileMark> {
        return databaseService.getFileMarks(pyFileFullPath, fileMarkType.value)
    }

    /**
     * Filter file marks by element text and line number (if provided).
     */
    fun filterPyFileMarks(fileMarks: MutableList<PyFileMark>, text: String, lineNumber: Int?): List<PyFileMark> {
        val filteredByTextFileMarks = fileMarks.stream()
                .filter { it.checkContent == text }
                .collect(Collectors.toList())

        return filterByBeginLineNumber(filteredByTextFileMarks, lineNumber)
    }

    /**
     * Get exception text for file mark.
     */
    fun getExceptionText(fileMark: PyFileMark): String? {
        val pyException = databaseService.getPyException(fileMark.exceptionId)

        return pyException?.exceptionText
    }

    /**
     * Get exception text for file mark.
     */
    fun getException(exceptionId: Int): PyException? = databaseService.getPyException(exceptionId)

    /**
     * Filter list of PyFileMark's by begin line if begin line not null
     */
    fun filterByBeginLineNumber(pyFileMarks: List<PyFileMark>, beginLine: Int?): List<PyFileMark> {
        return if (beginLine != null) {
            pyFileMarks.stream()
                    .filter { it.beginLine == beginLine }
                    .collect(Collectors.toList())
        } else {
            pyFileMarks
        }
    }

    /**
     * Filter list of [PyFileMark] by element content if it's not null
     */
    fun filterByElementContent(pyFileMarks: List<PyFileMark>, text: String?): List<PyFileMark> {
        return if (Objects.nonNull(text)) {
            pyFileMarks.stream()
                    .filter { it.checkContent == text }
                    .collect(Collectors.toList())

        } else {
            pyFileMarks
        }
    }
}