package sk.infinit.testmon.extensions

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.ServiceManager
import com.intellij.openapi.editor.Document
import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Computable
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.util.text.StringUtil
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getVirtualFileRelativePath
import sk.infinit.testmon.services.cache.Cache
import java.awt.Color
import java.awt.Font
import java.util.stream.Collectors


/**
 * Testmon EditorLinePainter implementation.
 */
class SuffixEditorLinePainter : EditorLinePainter() {

    /**
     * Get list of LineExtensionInfo's by Testmon database data. Draw exception description text.
     *
     * @return MutableCollection<LineExtensionInfo>
     */
    override fun getLineExtensions(project: Project, virtualFile: VirtualFile, lineNumber: Int)
            : MutableCollection<LineExtensionInfo> {
        val lineExtensionInfos = mutableListOf<LineExtensionInfo>()

        val document = FileDocumentManager.getInstance().getDocument(virtualFile) ?: return lineExtensionInfos

        if (lineNumber >= document.lineCount) {
            return lineExtensionInfos
        }

        val pyFileMarks = getPyFileMarks(project, virtualFile)

        val filteredPyFileMarks = filterPyFileMarks(pyFileMarks, document, lineNumber)

        for (fileMark in filteredPyFileMarks) {
            lineExtensionInfos.add(LineExtensionInfo(
                    "   ${fileMark.text}",
                    Color.RED,
                    null,
                    null, Font.PLAIN))
        }

        return lineExtensionInfos
    }

    /**
     * Get file marks from cache or from DB
     */
    private fun getPyFileMarks(project: Project, virtualFile: VirtualFile):
            List<PyFileMark> {
        val cacheService = ServiceManager.getService(project, Cache::class.java)
                ?: return ArrayList()

        val absoluteFilePath = virtualFile.path

        return cacheService.getPyFileMarks(absoluteFilePath, FileMarkType.SUFFIX) ?: ArrayList()
    }

    private fun filterPyFileMarks(fileMarksList: List<PyFileMark>, document: Document, lineNumber: Int): List<PyFileMark> {
        // Filter by line number
        val filteredByLineNumberFileMarks = fileMarksList.stream()
                .filter { it.beginLine == lineNumber }
                .collect(Collectors.toList())

        // Filter by content (could be multiline)
        val filteredByLineTextFileMarks = filteredByLineNumberFileMarks.stream()
                .filter { filterByContent(it, document, lineNumber) }
                .collect(Collectors.toList())

        // Deduplicate using exception text
        return filteredByLineTextFileMarks.distinctBy { it.text }
    }

    private fun filterByContent(fileMark: PyFileMark, document: Document, lineNumber: Int): Boolean {
        val fileMarkContent = fileMark.checkContent.trim()

        val lineStartOffset = document.getLineStartOffset(fileMark.beginLine)

        val lineElementOffset = StringUtil.indexOf(document.immutableCharSequence,
                fileMarkContent as CharSequence, lineStartOffset)

        val maxOffset = document.getLineEndOffset(document.lineCount - 1)
        if (lineElementOffset < 0 && lineElementOffset + fileMarkContent.length <= maxOffset) {
            return false
        }

        val documentContent = document.getText(TextRange(
                document.getLineStartOffset(lineNumber),
                lineElementOffset + fileMarkContent.length))

        return fileMarkContent == documentContent.trim()
    }
}
