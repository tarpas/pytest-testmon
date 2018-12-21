package sk.infinit.testmon.extensions

import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.vfs.VirtualFile
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getDatabaseServiceProjectComponent
import sk.infinit.testmon.getFileFullPath
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

        val document = FileDocumentManager.getInstance().getDocument(virtualFile) ?: return lineExtensionInfos

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
    private fun getPyFileMarks(project: Project, virtualFile: VirtualFile, lineNumber: Int, line: String):
            List<PyFileMark> {
        val psiElementErrorProvider = FileMarkProvider(getDatabaseServiceProjectComponent(project))

        // Update cache
        if (lineNumber == 0) {
            val fileFullPath = getFileFullPath(project, virtualFile) ?: return ArrayList()

            cachedPyFileMarks = psiElementErrorProvider
                    .getPyFileMarks(fileFullPath, FileMarkType.SUFFIX) as MutableList<PyFileMark>
        }

        return psiElementErrorProvider
                .filterPyFileMarks(cachedPyFileMarks, line, lineNumber)
    }

}