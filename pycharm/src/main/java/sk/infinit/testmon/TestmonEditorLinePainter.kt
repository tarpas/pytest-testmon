package sk.infinit.testmon

import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.editor.LineExtensionInfo
import com.intellij.openapi.editor.markup.EffectType
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
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
    override fun getLineExtensions(project: Project, virtualFile: VirtualFile, lineNumber: Int): MutableCollection<LineExtensionInfo> {
        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)

        val databaseFilePath = getProjectDatabaseFilePath(projectRootVirtualFile)

        val databaseService = DatabaseService(databaseFilePath)
        val pyExceptions = databaseService.getPyExceptions()

        for (pyException in pyExceptions) {
            if (lineNumber == pyException.lineNumber) {
                val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

                val pyFileFullPath = projectRootVirtualFile?.path + File.separator + virtualFileRelativePath

                if (pyFileFullPath == pyException.fileName) {
                    val fileMarks = databaseService.getExceptionFileMarks(pyException)

                    for (fileMark in fileMarks) {
                        if (FileMarkType.RED_UNDERLINE_DECORATION.value == fileMark.type) {
                            val lineExtensionInfo = LineExtensionInfo("     ${pyException.exceptionText}", Color.RED, EffectType.ROUNDED_BOX, null, Font.PLAIN)

                            return mutableListOf(lineExtensionInfo)
                        }
                    }
                }
            }
        }

        return mutableListOf()
    }
}