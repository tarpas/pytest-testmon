package sk.infinit.testmon.extensions

import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiManager
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getProjectRootDirectoryVirtualFile
import sk.infinit.testmon.getVirtualFileRelativePath
import java.io.File
import java.util.ArrayList
import java.util.stream.Collectors

/**
 * PsiElement error provider.
 */
class PsiElementErrorProvider {

    /**
     * Get PyFileMark's list by PsiElement. Common method for extensions
     * (as Annotator, EditorLinePainter, RelatedItemLineMarkerProvider).
     */
    fun getPyFileMarks(psiElement: PsiElement): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        val project = psiElement.project
        val virtualFile = psiElement.containingFile.virtualFile

        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)
                ?: return pyFileMarks

        val databaseService = DatabaseService.getInstance()

        val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

        val pyFileFullPath = projectRootVirtualFile.path + File.separator + virtualFileRelativePath

        val psiFile = PsiManager.getInstance(project).findFile(virtualFile)
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile!!)

        val lineNumber = document?.getLineNumber(psiElement.textOffset)

        val fileMarks = databaseService
                .getFileMarks(pyFileFullPath, lineNumber, FileMarkType.RED_UNDERLINE_DECORATION.value)

        for (fileMark in fileMarks) {
            if (fileMark.checkContent == psiElement.text) {

            }
        }

        return fileMarks.stream()
                .filter { it.checkContent == psiElement.text }
                .collect(Collectors.toList())
    }
}