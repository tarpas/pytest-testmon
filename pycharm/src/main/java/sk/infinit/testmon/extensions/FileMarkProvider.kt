package sk.infinit.testmon.extensions

import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getDatabaseServiceProjectComponent
import sk.infinit.testmon.getProjectRootDirectoryVirtualFile
import sk.infinit.testmon.getVirtualFileRelativePath
import java.io.File
import java.util.ArrayList
import java.util.stream.Collectors

/**
 * File mark provider. Middle layer between database API and IntelliJ UI extensions.
 */
class FileMarkProvider {

    /**
     * Get PyFileMark's list. Common method for extensions.
     *
     * This method will filter file marks by text and line number.
     *
     * Line number can be null. In this case it don't filter by line number and return result list.
     */
    fun getFilteredPyFileMarks(project: Project, virtualFile: VirtualFile,
                               elementText: String, fileMarkType: FileMarkType,
                               lineNumber: Int?): List<PyFileMark> {
        val fileMarks = getPyFileMarks(project, virtualFile, fileMarkType)

        return filterPyFileMarks(fileMarks.toMutableList(), elementText, lineNumber)
    }

    /**
     * Get PyFileMark's by py file full path.
     */
    fun getPyFileMarks(project: Project, virtualFile: VirtualFile, fileMarkType: FileMarkType): List<PyFileMark> {
        val pyFileFullPath = getPsiFileFullPath(project, virtualFile)
                ?: return ArrayList()

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
     * Get full path of PsiFile.
     */
    private fun getPsiFileFullPath(project: Project, virtualFile: VirtualFile): String? {
        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)
                ?: return null

        val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

        return projectRootVirtualFile.path + File.separator + virtualFileRelativePath
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