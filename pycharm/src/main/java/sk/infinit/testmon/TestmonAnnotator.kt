package sk.infinit.testmon

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.Annotator
import com.intellij.psi.PsiElement
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiDocumentManager
import sk.infinit.testmon.database.DatabaseService
import java.io.File
import com.intellij.psi.PsiManager
import com.jetbrains.python.psi.PyStatement
import sk.infinit.testmon.database.FileMarkType

/**
 * Testmon Annotator implementation.
 */
class TestmonAnnotator : Annotator {

    /**
     * Draw underline decorations by Testmon exceptions data.
     */
    override fun annotate(psiElement: PsiElement, annotationHolder: AnnotationHolder) {
        if (psiElement is PyStatement) {
            val project = psiElement.project
            val virtualFile = psiElement.containingFile.virtualFile

            val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)
                    ?: return

            val databaseService = DatabaseService.getInstance()

            val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

            val pyFileFullPath = projectRootVirtualFile.path + File.separator + virtualFileRelativePath

            val psiFile = PsiManager.getInstance(project).findFile(virtualFile)
            val document = PsiDocumentManager.getInstance(project).getDocument(psiFile!!)

            val lineNumber = document?.getLineNumber(psiElement.textOffset)

            val fileMarks = databaseService
                    .getFileMarks(pyFileFullPath, lineNumber, FileMarkType.RED_UNDERLINE_DECORATION.value)

            for (fileMark in fileMarks) {
                try {
                    if (fileMark.checkContent == psiElement.text) {
                        val startOffset = psiElement.textRange.startOffset
                        val endOffset = psiElement.textRange.endOffset

                        val range = TextRange(startOffset, endOffset)

                        val pyException = databaseService.getPyException(fileMark.exceptionId)

                        val annotation = annotationHolder.createErrorAnnotation(range, pyException?.exceptionText)

                        annotation.tooltip = pyException?.exceptionText
                    }
                } catch (exception: Exception) {
                    logErrorMessage(exception)
                }
            }
        }
    }
}
