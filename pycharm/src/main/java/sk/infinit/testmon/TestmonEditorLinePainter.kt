package sk.infinit.testmon

import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.editor.markup.EffectType
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import sk.infinit.testmon.database.DatabaseService
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
    override fun getLineExtensions(project: Project, virtualFile: VirtualFile, lineNumber: Int): MutableCollection<LineExtensionInfo> {
        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)

        val databaseService = DatabaseService.getInstance(projectRootVirtualFile?.path)

        val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)
        val pyFileFullPath = projectRootVirtualFile?.path + File.separator + virtualFileRelativePath

        val fileMarks = databaseService.getRedUnderlineDecorationFileMarks(pyFileFullPath, lineNumber)

        val lineExtensionInfos = mutableListOf<LineExtensionInfo>()

        for (fileMark in fileMarks) {
            val lineExtensionInfo = LineExtensionInfo(
                    "     ${fileMark.text}",
                    Color.RED,
                    EffectType.ROUNDED_BOX,
                    null, Font.PLAIN)

            lineExtensionInfos.add(lineExtensionInfo)
        }

        return lineExtensionInfos
    }
}