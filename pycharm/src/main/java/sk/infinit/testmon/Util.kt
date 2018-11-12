package sk.infinit.testmon

import com.intellij.notification.Notification
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.editor.EditorFactory
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import java.io.File
import java.lang.Exception

/**
 * Log error message to Notifications Bus.
 *
 * @param message - source message to log as Error message
 */
fun logErrorMessage(message: String) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID, "Testmon message", message, NotificationType.ERROR))
}

/**
 * Log exception message to Notifications Bus.
 *
 * @param exception - source exception to log as Error message
 */
fun logErrorMessage(exception: Exception) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID, "Testmon message", exception.message.toString(), NotificationType.ERROR))
}

/**
 * Get virtual file relative path.
 *
 * @return String
 */
fun getVirtualFileRelativePath(virtualFile: VirtualFile, projectRootVirtualFile: VirtualFile?): String? = VfsUtilCore.getRelativePath(virtualFile, projectRootVirtualFile!!)

/**
 * Get Project root directory VirtualFile
 *
 * @return VirtualFile?
 */
fun getProjectRootDirectoryVirtualFile(project: Project, virtualFile: VirtualFile): VirtualFile? = ProjectFileIndex.SERVICE.getInstance(project).getContentRootForFile(virtualFile)

/**
 * Return VirtualFile by full real path to file.
 */
fun findVirtualFile(filePath: String?) = VfsUtil.findFileByIoFile(File(filePath), false)

/**
 * Get Editor object for PsiFile.
 */
fun getEditor(project: Project, psiFile: PsiFile): Editor? {
    val document = PsiDocumentManager.getInstance(project).getDocument(psiFile)

    val editors = EditorFactory.getInstance().getEditors(document!!)

    if (editors.isNotEmpty()) {
        return editors[0]
    }

    return null
}