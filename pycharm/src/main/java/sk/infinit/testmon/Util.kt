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
import sk.infinit.testmon.database.DatabaseServiceProjectComponent
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.lang.Exception

/**
 * Log error message to Notifications Bus.
 *
 * @param message - source message to log as Error message
 */
fun logErrorMessage(message: String, project: Project) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID,
            "Runtime-info plugin", message, NotificationType.ERROR), project)
}

/**
 * Log exception message to Notifications Bus.
 *
 * @param exception - source exception to log as Error message
 */
fun logErrorMessage(exception: Exception, project: Project) {
    val message = if (exception.message != null) {
        exception.message
    } else {
        getStackTrace(exception)
    }

    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID,
            "Runtime-info plugin", message!!, NotificationType.ERROR), project)
}

/**
 * Get virtual file relative path.
 *
 * @return String
 */
fun getVirtualFileRelativePath(virtualFile: VirtualFile, projectRootVirtualFile: VirtualFile): String?
        = VfsUtilCore.getRelativePath(virtualFile, projectRootVirtualFile)

/**
 * Get Project root directory VirtualFile
 *
 * @return VirtualFile?
 */
fun getProjectRootDirectoryVirtualFile(project: Project, virtualFile: VirtualFile): VirtualFile?
        = ProjectFileIndex.SERVICE.getInstance(project).getContentRootForFile(virtualFile)

/**
 * Return VirtualFile by full real path to file.
 */
fun findVirtualFile(filePath: String?): VirtualFile? {
    return if (filePath != null) {
        VfsUtil.findFileByIoFile(File(filePath), false)
    } else {
        null
    }
}

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

/**
 * Convert Throwable object to string
 */
fun getStackTrace(throwable: Throwable): String {
    val stringWriter = StringWriter()
    val printWriter = PrintWriter(stringWriter, true)

    throwable.printStackTrace(printWriter)

    return stringWriter.buffer.toString()
}

/**
 * Get DatabaseServiceProjectComponent instance
 */
fun getDatabaseServiceProjectComponent(project: Project)
        = project.getComponent(DatabaseServiceProjectComponent::class.java) as DatabaseServiceProjectComponent


/**
 * Check is plugin extensions disabled or enabled.
 */
fun isExtensionsDisabled(project: Project) = !getDatabaseServiceProjectComponent(project).enabled
