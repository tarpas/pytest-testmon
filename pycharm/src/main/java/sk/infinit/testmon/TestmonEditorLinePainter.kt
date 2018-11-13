package sk.infinit.testmon

import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.editor.markup.EffectType
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiManager
import com.jetbrains.python.psi.PyStatement
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.FileMarkType
import java.awt.Color
import java.awt.Font
import java.io.File

/**
 * Testmon EditorLinePainter implementation.
 */
class TestmonEditorLinePainter : EditorLinePainter() {

    /**
     * Get list of LineExtensionInfo's by Testmon database data. Draw exception description text.
     *
     * @return MutableCollection<LineExtensionInfo>
     */
    override fun getLineExtensions(project: Project, virtualFile: VirtualFile, lineNumber: Int)
            : MutableCollection<LineExtensionInfo> {
        val lineExtensionInfos = mutableListOf<LineExtensionInfo>()

        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)
                ?: return lineExtensionInfos

        val databaseService = DatabaseService.getInstance()

        val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)
        val pyFileFullPath = projectRootVirtualFile.path + File.separator + virtualFileRelativePath

        val fileMarks = databaseService
                .getFileMarks(pyFileFullPath, lineNumber, FileMarkType.RED_UNDERLINE_DECORATION.value)

        val psiElement = getPsiElementAtLine(project, virtualFile, lineNumber)

        if (psiElement is PyStatement) {
            for (fileMark in fileMarks) {
                if (fileMark.checkContent == psiElement.text) {
                    val lineExtensionInfo = LineExtensionInfo(
                            "     ${fileMark.text}",
                            Color.RED,
                            EffectType.ROUNDED_BOX,
                            null, Font.PLAIN)

                    lineExtensionInfos.add(lineExtensionInfo)
                }
            }
        }

        return lineExtensionInfos
    }

    /**
     * Get PsiElement by line number.
     */
    private fun getPsiElementAtLine(project: Project, virtualFile: VirtualFile, lineNumber: Int)
            : PsiElement {
        val psiFile = PsiManager.getInstance(project).findFile(virtualFile)

        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile!!)
        val offset = document?.getLineStartOffset(lineNumber)

        val psiElement = psiFile.viewProvider.findElementAt(offset!!)

        return if (document.getLineNumber(psiElement!!.textOffset) != lineNumber) {
            psiElement.nextSibling
        } else {
            psiElement
        }
    }
}