package sk.infinit.testmon.extensions

import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.module.Module
import com.intellij.openapi.module.ModuleServiceManager
import com.intellij.openapi.module.ModuleUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.vfs.VirtualFile
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.getFileFullPath
import sk.infinit.testmon.getModuleRuntimeInfoFile
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

        val module = ModuleUtil.findModuleForFile(virtualFile, project)
                ?: return lineExtensionInfos

        val moduleRuntimeInfoFile = getModuleRuntimeInfoFile(module)
                ?: return lineExtensionInfos

        if (moduleRuntimeInfoFile.isBlank()) {
            return lineExtensionInfos
        }

        val document = FileDocumentManager.getInstance().getDocument(virtualFile) ?: return lineExtensionInfos

        val line = document.getText(TextRange(
                document.getLineStartOffset(lineNumber),
                document.getLineEndOffset(lineNumber)))

        val pyFileMarks = getPyFileMarks(project, module, virtualFile, lineNumber, line)

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
    private fun getPyFileMarks(project: Project, module: Module, virtualFile: VirtualFile, lineNumber: Int, lineText: String):
            List<PyFileMark> {
        val cacheService = ModuleServiceManager.getService(module, Cache::class.java)
                ?: return ArrayList()

        val fileFullPath = getFileFullPath(project, virtualFile) ?: return ArrayList()

        val fileMarks = cacheService.getSuffixFileMarks(fileFullPath) as MutableList<PyFileMark>

        val filteredByTextFileMarks = fileMarks.stream()
                .filter { it.checkContent == lineText }
                .collect(Collectors.toList())

        return filterByBeginLineNumber(filteredByTextFileMarks, lineNumber)
    }

    private fun filterByBeginLineNumber(pyFileMarks: List<PyFileMark>, beginLine: Int?): List<PyFileMark> {
        return if (beginLine != null) {
            pyFileMarks.stream()
                    .filter { it.beginLine == beginLine }
                    .collect(Collectors.toList())
        } else {
            pyFileMarks
        }
    }
}