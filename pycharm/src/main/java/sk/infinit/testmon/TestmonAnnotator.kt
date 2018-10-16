package sk.infinit.testmon

import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.Annotator
import com.intellij.openapi.editor.*
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.openapi.util.TextRange
import sk.infinit.testmon.database.DatabaseService
import java.io.File
import com.intellij.psi.PsiFile
import sk.infinit.testmon.database.FileMarkType


/**
 * Testmon Annotator implementation.
 */
class TestmonAnnotator : Annotator {

    /**
     * Draw underline decorations by Testmon exceptions data.
     */
    override fun annotate(psiElement: PsiElement, annotationHolder: AnnotationHolder) {
        if (psiElement is PsiFile) {
            val project = psiElement.project
            val virtualFile = psiElement.containingFile.virtualFile

            val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)

            val databaseFilePath = getProjectDatabaseFilePath(projectRootVirtualFile)

            val editor = EditorFactory.getInstance().allEditors[0] // FileEditorManager manager = FileEditorManager.getInstance(ModificationsPlugin.myProject);

            val databaseService = DatabaseService(databaseFilePath)
            val pyExceptions = databaseService.getPyExceptions()

            for (pyException in pyExceptions) {
                val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

                val pyFileFullPath = projectRootVirtualFile?.path + File.separator + virtualFileRelativePath

                if (pyFileFullPath == pyException.fileName) {
                    val fileMarks = databaseService.getExceptionFileMarks(pyException)

                    for (fileMark in fileMarks) {
                        if (FileMarkType.RED_UNDERLINE_DECORATION.value == fileMark.type) {
                            val currentVirtualFile = FileDocumentManager.getInstance().getFile(editor.document)

                            val currentVirtualFileRelativePath = getVirtualFileRelativePath(currentVirtualFile!!, projectRootVirtualFile)

                            val currentPyFileFullPath = projectRootVirtualFile?.path + File.separator + currentVirtualFileRelativePath

                            if (fileMark.fileName == currentPyFileFullPath) {
                                try {
                                    val logicalStartPosition = LogicalPosition(fileMark.beginLine, fileMark.beginCharacter)
                                    val logicalEndPosition = LogicalPosition(fileMark.endLine, fileMark.endCharacter)

                                    val startOffset = editor.logicalPositionToOffset(logicalStartPosition)
                                    val endOffset = editor.logicalPositionToOffset(logicalEndPosition)

                                    val range = TextRange(startOffset, endOffset)

                                    val annotation = annotationHolder.createErrorAnnotation(range, pyException.exceptionText)

                                    annotation.tooltip = pyException.description
                                } catch (exception: Exception) {
                                    logErrorMessage(exception.message!!)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}