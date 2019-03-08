package sk.infinit.testmon.extensions

import com.intellij.openapi.components.ServiceManager
import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.vfs.VirtualFile
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

        val line = document.getText(TextRange(
                document.getLineStartOffset(lineNumber),
                document.getLineEndOffset(lineNumber)))

        val pyFileMarks = getPyFileMarks(project, virtualFile, lineNumber, line)

        for (fileMark in pyFileMarks) {
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
    private fun getPyFileMarks(project: Project, virtualFile: VirtualFile, lineNumber: Int, lineText: String):
            List<PyFileMark> {
        val cacheService = ServiceManager.getService(project, Cache::class.java)
                ?: return ArrayList()

        val absoluteFilePath = virtualFile.path

        val fileMarksList = cacheService.getPyFileMarks(absoluteFilePath, FileMarkType.SUFFIX) ?: ArrayList()

        val fileMarks = fileMarksList as MutableList<PyFileMark>

        // Filter by line text.
        val filteredByLineTextFileMarks = fileMarks.stream()
                .filter { it.checkContent == lineText }
                .collect(Collectors.toList())

        // Filter by line number.
        val filteredByLineNumberFileMarks = filteredByLineTextFileMarks.stream()
                .filter { it.beginLine == lineNumber }
                .collect(Collectors.toList())

        // Deduplicate using exception text
        return filteredByLineNumberFileMarks.distinctBy { it.text }
    }
}