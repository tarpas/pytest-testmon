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
import sk.infinit.testmon.getFileFullPath
import com.intellij.openapi.module.ModuleServiceManager
import sk.infinit.testmon.services.cache.Cache
import com.intellij.openapi.module.ModuleUtil
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.isRuntimeInfoDisabledForModule

/**
 * Runtime info external annotator.
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

        val module = ModuleUtil.findModuleForFile(psiFile)
                ?: return redUnderlineAnnotations

        if (isRuntimeInfoDisabledForModule(module)) {
        val document = psiFile.viewProvider.document ?: return redUnderlineAnnotations

        if (isExtensionsDisabled(project)) {
            return redUnderlineAnnotations
        }

        val cacheService = ModuleServiceManager.getService(module, Cache::class.java)
                ?: return redUnderlineAnnotations

        val fileFullPath = getFileFullPath(project, psiFile.virtualFile)
                ?: return redUnderlineAnnotations

        val fileMarks = cacheService.getPyFileMarks(fileFullPath, FileMarkType.RED_UNDERLINE_DECORATION)
                ?: return redUnderlineAnnotations

        for (fileMark in fileMarks) {
            val fileMarkContent = fileMark.checkContent.trim()

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
                val exceptionText = psiElementErrorProvider.getExceptionText(fileMark) ?: continue
            if (lineNumber == fileMark.beginLine) {
                val exceptionText = fileMark.exception?.exceptionText

                redUnderlineAnnotations.add(RedUnderlineDecorationAnnotation(exceptionText, psiElement))
                if (exceptionText != null) {
                    redUnderlineAnnotations.add(RedUnderlineDecorationAnnotation(exceptionText, psiElement))
                }
            }
        }

        return redUnderlineAnnotations
    }
}