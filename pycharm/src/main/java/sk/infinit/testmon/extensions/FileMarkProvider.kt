package sk.infinit.testmon.extensions

import com.intellij.openapi.project.Project
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getDatabaseServiceProjectComponent
import java.util.stream.Collectors

/**
 * File mark provider. Middle layer between database API and IntelliJ UI extensions.
 */
class FileMarkProvider {

    /**
     * Get PyFileMark's by py file full path.
     */
    fun getPyFileMarks(project: Project, pyFileFullPath: String, fileMarkType: FileMarkType): List<PyFileMark> {
        return getDatabaseServiceProjectComponent(project).getFileMarks(pyFileFullPath, fileMarkType.value)
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
    fun getExceptionText(fileMark: PyFileMark, project: Project): String? {
        val pyException = getDatabaseServiceProjectComponent(project).getPyException(fileMark.exceptionId)

        return pyException?.exceptionText
    }

    /**
     * Filter list of PyFileMark's by begin line if begin line not null
     */
    private fun filterByBeginLineNumber(pyFileMarks: List<PyFileMark>, beginLine: Int?): List<PyFileMark> {
        return if (beginLine != null) {
            pyFileMarks.stream()
                    .filter { it.beginLine == beginLine }
                    .collect(Collectors.toList())
        } else {
            pyFileMarks
        }
    }
}