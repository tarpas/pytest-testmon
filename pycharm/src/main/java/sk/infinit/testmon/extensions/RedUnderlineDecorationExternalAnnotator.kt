package sk.infinit.testmon.extensions

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.ExternalAnnotator
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.util.Computable
import com.intellij.openapi.util.text.StringUtil
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.isExtensionsDisabled

/**
 * Testmon external annotator.
 */
class RedUnderlineDecorationExternalAnnotator
    : ExternalAnnotator<PsiFile, List<RedUnderlineDecorationAnnotation>>() {

    /**
     * Create annotations by #redUnderlineAnnotations list.
     */
    override fun apply(file: PsiFile, redUnderlineAnnotations: List<RedUnderlineDecorationAnnotation>?,
                       annotationHolder: AnnotationHolder) {
        if (redUnderlineAnnotations == null) {
            return
        }

        for (redUnderlineAnnotation in redUnderlineAnnotations) {
            val annotation = annotationHolder
                    .createErrorAnnotation(redUnderlineAnnotation.psiElement!!, redUnderlineAnnotation.message)

            annotation.tooltip = redUnderlineAnnotation.message
        }
    }

    /**
     * Return PsiFile instance.
     */
    override fun collectInformation(psiFile: PsiFile, editor: Editor, hasErrors: Boolean): PsiFile? {
        return psiFile
    }

    /**
     * Collect PyFileMark errors to RedUnderlineDecorationAnnotation list.
     */
    override fun doAnnotate(psiFile: PsiFile?): List<RedUnderlineDecorationAnnotation>? {
        val redUnderlineAnnotations = mutableListOf<RedUnderlineDecorationAnnotation>()

        val project = psiFile?.project ?: return redUnderlineAnnotations

        if (isExtensionsDisabled(project)) {
            return redUnderlineAnnotations
        }

        val psiElementErrorProvider = PsiElementErrorProvider()

        val fileMarks = psiElementErrorProvider
                .getPyFileMarks(psiFile, FileMarkType.RED_UNDERLINE_DECORATION)

        for (fileMark in fileMarks) {
            val document = psiFile.viewProvider.document

            val fileMarkContent = fileMark.checkContent

            val elementOffset = StringUtil
                    .indexOf(document?.immutableCharSequence!!, fileMarkContent as CharSequence)

            if (elementOffset < 0) {
                continue
            }

            val psiElement = ApplicationManager.getApplication()
                    .runReadAction(Computable<PsiElement> {
                        PsiTreeUtil.findElementOfClassAtRange(psiFile, elementOffset,
                                elementOffset + fileMarkContent.length, PsiElement::class.java)
                    })

            val lineNumber = document.getLineNumber(elementOffset)

            if (lineNumber == fileMark.beginLine) {
                val exceptionText = psiElementErrorProvider.getExceptionText(fileMark)

                redUnderlineAnnotations.add(RedUnderlineDecorationAnnotation(exceptionText!!, psiElement))
            }
        }

        return redUnderlineAnnotations
    }
}