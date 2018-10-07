package sk.infinit.testmon

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.Annotator
import com.intellij.openapi.editor.EditorFactory
import com.intellij.psi.PsiElement
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.editor.LogicalPosition
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import sk.infinit.testmon.database.DatabaseService
import java.io.File


/**
 * Testmon Annotator implementation.
 */
class TestmonAnnotator : Annotator {

    val alreadyDisplayedExceptionIds: MutableList<Int> = ArrayList()

    override fun annotate(psiElement: PsiElement, annotationHolder: AnnotationHolder) {
        val project = psiElement.project
        val virtualFile = psiElement.containingFile.virtualFile

        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)

        val databaseFilePath = getProjectDatabaseFilePath(projectRootVirtualFile)

        val editor = EditorFactory.getInstance().allEditors[0]

        val databaseService = DatabaseService(databaseFilePath)
        val pyExceptions = databaseService.getPyExceptions()

        for (pyException in pyExceptions) {
            if (!alreadyDisplayedExceptionIds.contains(pyException.id)) {
                val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

                val pyFileFullPath = projectRootVirtualFile?.path + File.separator + virtualFileRelativePath

                if (pyFileFullPath == pyException.fileName) {
                    val logicalStartPosition = LogicalPosition(pyException.lineNumber, 0)
                    val logicalEndPosition = LogicalPosition(pyException.lineNumber, 10)

                    val startOffset = editor.logicalPositionToOffset(logicalStartPosition)
                    val endOffset = editor.logicalPositionToOffset(logicalEndPosition)

                    val range = TextRange(startOffset, endOffset)

                    val annotation = annotationHolder.createErrorAnnotation(range, pyException.exceptionText)

                    annotation.tooltip = pyException.description

                    alreadyDisplayedExceptionIds.add(pyException.id)
                }
            }
        }
    }

    /**
     * Get project Sqlite database file path.
     */
    private fun getProjectDatabaseFilePath(projectRootVirtualFile: VirtualFile?) =
            projectRootVirtualFile?.path + File.separator + "runtime_test_report.db"

    /**
     * Get virtual file relative path.
     *
     * @return String
     */
    private fun getVirtualFileRelativePath(virtualFile: VirtualFile, projectRootVirtualFile: VirtualFile?): String?
            = VfsUtilCore.getRelativePath(virtualFile, projectRootVirtualFile!!)

    /**
     * Get Project root directory VirtualFile
     *
     * @return VirtualFile?
     */
    private fun getProjectRootDirectoryVirtualFile(project: Project, virtualFile: VirtualFile): VirtualFile?
            = ProjectFileIndex.SERVICE.getInstance(project).getContentRootForFile(virtualFile)
}