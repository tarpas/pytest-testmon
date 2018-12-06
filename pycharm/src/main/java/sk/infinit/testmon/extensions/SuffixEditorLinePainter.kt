package sk.infinit.testmon.extensions

import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.editor.markup.EffectType
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiManager
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.isExtensionsDisabled
import java.awt.Color
import java.awt.Font

/**
 * Testmon EditorLinePainter implementation.
 */
class SuffixEditorLinePainter : EditorLinePainter() {
    private var cachedPyFileMarks = mutableListOf<PyFileMark>()

    /**
     * Get list of LineExtensionInfo's by Testmon database data. Draw exception description text.
     *
     * @return MutableCollection<LineExtensionInfo>
     */
    override fun getLineExtensions(project: Project, virtualFile: VirtualFile, lineNumber: Int)
            : MutableCollection<LineExtensionInfo> {
        val lineExtensionInfos = mutableListOf<LineExtensionInfo>()

        if (isExtensionsDisabled(project)) {
            return lineExtensionInfos
        }

        val psiElement = getPsiElementAtLine(project, virtualFile, lineNumber)
                ?: return lineExtensionInfos

        val pyFileMarks = getPyFileMarks(lineNumber, project, virtualFile, psiElement)

        for (fileMark in pyFileMarks) {
            lineExtensionInfos.add(LineExtensionInfo(
                    "   ${fileMark.text}",
                    Color.RED,
                    EffectType.ROUNDED_BOX,
                    null, Font.PLAIN))
        }

        return lineExtensionInfos
    }


    /**
     * Get file marks from cache or from DB
     */
    private fun getPyFileMarks(lineNumber: Int, project: Project, virtualFile: VirtualFile, psiElement: PsiElement):
            List<PyFileMark> {
        val psiElementErrorProvider = PsiElementErrorProvider()

        val psiElementLineNumber = getPsiElementLineNumber(project, virtualFile, psiElement)

        // Update cache
        if (lineNumber == 0) {
            cachedPyFileMarks = psiElementErrorProvider.getPyFileMarks(psiElement, FileMarkType.SUFFIX) as MutableList<PyFileMark>
        }

        return psiElementErrorProvider
                .filterPyFileMarks(cachedPyFileMarks, psiElement, psiElementLineNumber)
    }

    /**
     * Get PsiElement by line number.
     */
    private fun getPsiElementAtLine(project: Project, virtualFile: VirtualFile, lineNumber: Int)
            : PsiElement? {
        val psiFile = PsiManager.getInstance(project).findFile(virtualFile)
                ?: return null

        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile)
        val offset = document?.getLineStartOffset(lineNumber)

        val psiElement = psiFile.viewProvider.findElementAt(offset!!)
                ?: return null

        return if (document.getLineNumber(psiElement.textOffset) != lineNumber) {
            psiElement.nextSibling
        } else {
            psiElement
        }
    }

    /**
     * Get PsiElement line number. This line number can differ from
     * override fun getLineExtensions(project: Project, virtualFile: VirtualFile, lineNumber: Int)
     *
     * and contains real line number including new line symbols ('\n').
     */
    private fun getPsiElementLineNumber(project: Project, virtualFile: VirtualFile,
                                        psiElement: PsiElement): Int? {
        val psiFile = PsiManager.getInstance(project).findFile(virtualFile)
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile!!)

        return document?.getLineNumber(psiElement.textOffset)
    }
}