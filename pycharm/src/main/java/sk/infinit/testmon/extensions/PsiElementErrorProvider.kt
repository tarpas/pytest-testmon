package sk.infinit.testmon.extensions

import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getProjectRootDirectoryVirtualFile
import sk.infinit.testmon.getVirtualFileRelativePath
import java.io.File
import java.util.ArrayList
import java.util.stream.Collectors

/**
 * PsiElement error provider. Middle layer between database API and IntelliJ UI extensions.
 */
class PsiElementErrorProvider {

    /**
     * Get PyFileMark's list by PsiElement. Common method for extensions
     *
     * This method will filter file marks by text and line number.
     *
     * Line number can be null. In this case it don't filter by line number and return result list.
     */
    fun getFilteredPyFileMarks(psiElement: PsiElement, fileMarkType: FileMarkType, lineNumber: Int?): List<PyFileMark> {
        val fileMarks = getPyFileMarks(psiElement, fileMarkType)

        return filterPyFileMarks(fileMarks.toMutableList(), psiElement, lineNumber)
    }

    /**
     * Get PyFileMark's by PsiElement py file full path.
     */
    fun getPyFileMarks(psiElement: PsiElement, fileMarkType: FileMarkType): List<PyFileMark> {
        val pyFileFullPath = getPsiFileFullPath(psiElement.project, psiElement.containingFile.virtualFile)
                ?: return ArrayList()

        return DatabaseService.getInstance().getFileMarks(pyFileFullPath, fileMarkType.value)
    }


    fun filterPyFileMarks(fileMarks: MutableList<PyFileMark>, psiElement: PsiElement, lineNumber: Int?): List<PyFileMark> {
        val filteredByTextFileMarks = fileMarks.stream()
                .filter { it.checkContent == psiElement.text }
                .collect(Collectors.toList())

        return filterByBeginLineNumber(filteredByTextFileMarks, lineNumber)
    }

    /**
     * Get exception text for file mark.
     */
    fun getExceptionText(fileMark: PyFileMark): String? {
        val pyException = DatabaseService.getInstance().getPyException(fileMark.exceptionId)

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