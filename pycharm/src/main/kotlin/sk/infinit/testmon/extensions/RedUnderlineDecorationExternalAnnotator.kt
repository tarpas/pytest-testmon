package sk.infinit.testmon.extensions

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.ExternalAnnotator
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.ServiceManager
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.util.Computable
import com.intellij.openapi.util.text.StringUtil
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import sk.infinit.testmon.getVirtualFileRelativePath
import sk.infinit.testmon.services.cache.Cache
import sk.infinit.testmon.database.FileMarkType

/**
 * Runtime info external annotator.
 */
class RedUnderlineDecorationExternalAnnotator
    : ExternalAnnotator<PsiFile, List<RedUnderlineDecorationExternalAnnotator.RedUnderlineDecorationAnnotation>>() {

    /**
     * Create annotations by #redUnderlineAnnotations list.
     */
    override fun apply(file: PsiFile, redUnderlineAnnotations: List<RedUnderlineDecorationAnnotation>?,
                       annotationHolder: AnnotationHolder) {
        if (redUnderlineAnnotations == null) {
            return
        }

        for (redUnderlineAnnotation in redUnderlineAnnotations) {
            val psiElement = redUnderlineAnnotation.psiElement

            if (psiElement != null) {
                val annotation = annotationHolder
                        .createErrorAnnotation(psiElement, redUnderlineAnnotation.message)

                annotation.tooltip = redUnderlineAnnotation.message
            }
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

        val document = psiFile.viewProvider.document ?: return redUnderlineAnnotations

        val fileRelativePath = getVirtualFileRelativePath(project, psiFile.virtualFile)
                ?: return redUnderlineAnnotations

        val cacheService = ServiceManager.getService(project, Cache::class.java)
                ?: return redUnderlineAnnotations

        val fileMarks = cacheService.getPyFileMarks(fileRelativePath, FileMarkType.RED_UNDERLINE_DECORATION)
                ?: return redUnderlineAnnotations

        for (fileMark in fileMarks) {
            val fileMarkContent = fileMark.checkContent.trim()

            if (fileMark.beginLine >= document.lineCount) {
                continue
            }

            val lineStartOffset = document.getLineStartOffset(fileMark.beginLine)

            if (lineStartOffset < 0) {
                continue
            }

            val lineElementOffset = StringUtil.indexOf(document.immutableCharSequence,
                    fileMarkContent as CharSequence, lineStartOffset)

            if (lineElementOffset < 0) {
                continue
            }

            val psiElement = ApplicationManager.getApplication()
                    .runReadAction(Computable<PsiElement> {
                        PsiTreeUtil.findElementOfClassAtRange(psiFile, lineElementOffset,
                                lineElementOffset + fileMarkContent.length, PsiElement::class.java)
                    })

            val lineNumber = document.getLineNumber(lineElementOffset)

            if (psiElement != null && lineNumber == fileMark.beginLine) {
                val exceptionText = fileMark.exception?.exceptionText

                if (exceptionText != null) {
                    redUnderlineAnnotations.add(RedUnderlineDecorationAnnotation(exceptionText, psiElement))
                }
            }
        }

        return redUnderlineAnnotations
    }

    class RedUnderlineDecorationAnnotation(val message: String, val psiElement: PsiElement?)
}