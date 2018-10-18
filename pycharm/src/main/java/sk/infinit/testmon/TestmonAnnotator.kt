package sk.infinit.testmon

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.Annotator
import com.intellij.openapi.editor.*
import com.intellij.psi.PsiElement
import com.intellij.openapi.util.TextRange
import sk.infinit.testmon.database.DatabaseService
import java.io.File
import com.intellij.psi.PsiFile

/**
 * Testmon Annotator implementation.
 */
class TestmonAnnotator : Annotator {

    /**
     * Draw underline decorations by Testmon exceptions data.
     */
    override fun annotate(psiElement: PsiElement, annotationHolder: AnnotationHolder) {
        if (psiElement is PsiFile) {
            val project = psiElement.project
            val virtualFile = psiElement.containingFile.virtualFile

            val editor = getEditor(project, psiElement) ?: return

            val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)

            val databaseService = DatabaseService.getInstance(projectRootVirtualFile?.path)

            val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

            val pyFileFullPath = projectRootVirtualFile?.path + File.separator + virtualFileRelativePath

            val fileMarks = databaseService.getRedUnderlineDecorationFileMarks(pyFileFullPath)

            for (fileMark in fileMarks) {
                try {
                    val logicalStartPosition = LogicalPosition(fileMark.beginLine, fileMark.beginCharacter)
                    val logicalEndPosition = LogicalPosition(fileMark.endLine, fileMark.endCharacter)

                    val startOffset = editor.logicalPositionToOffset(logicalStartPosition)
                    val endOffset = editor.logicalPositionToOffset(logicalEndPosition)

                    val range = TextRange(startOffset, endOffset)

                    val pyException = databaseService.getPyException(fileMark.exceptionId)

                    val annotation = annotationHolder.createErrorAnnotation(range, pyException?.exceptionText)

                    annotation.tooltip = pyException?.description
                } catch (exception: Exception) {
                    logErrorMessage(exception.message!!)
                }
            }
        }
    }
}
