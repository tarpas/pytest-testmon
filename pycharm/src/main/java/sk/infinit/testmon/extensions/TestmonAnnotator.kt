package sk.infinit.testmon.extensions

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.Annotator
import com.intellij.psi.PsiElement
import com.intellij.openapi.util.TextRange
import sk.infinit.testmon.database.DatabaseService
import com.jetbrains.python.psi.PyStatement

/**
 * Testmon Annotator implementation.
 */
class TestmonAnnotator : Annotator {

    /**
     * Draw underline decorations by Testmon exceptions data.
     */
    override fun annotate(psiElement: PsiElement, annotationHolder: AnnotationHolder) {
        if (psiElement is PyStatement) {
            val testmonErrorProvider = PsiElementErrorProvider()
            val databaseService = DatabaseService.getInstance()

            val fileMarks = testmonErrorProvider.getPyFileMarks(psiElement)

            for (fileMark in fileMarks) {
                val startOffset = psiElement.textRange.startOffset
                val endOffset = psiElement.textRange.endOffset

                val range = TextRange(startOffset, endOffset)

                val pyException = databaseService.getPyException(fileMark.exceptionId)

                val annotation = annotationHolder.createErrorAnnotation(range, pyException?.exceptionText)

                annotation.tooltip = pyException?.exceptionText
            }
        }
    }
}
