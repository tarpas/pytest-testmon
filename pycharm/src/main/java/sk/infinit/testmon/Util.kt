package sk.infinit.testmon

import com.intellij.notification.Notification
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import com.intellij.openapi.module.Module
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.util.Key
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.lang.Exception

/**
 * File name for Sqlite database files.
 */
const val DATABASE_FILE_NAME = ".runtime_info0"

/**
 * Key for module database file path.
 */
val MODULE_DATABASE_FILES_KEY = Key.create<List<String>>(DATABASE_FILE_NAME)

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
 * Log information message.
 */
fun logInfoMessage(message: String, project: Project) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID,
            "Runtime-info plugin", message, NotificationType.INFORMATION), project)
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
 * Convert Throwable object to string
 */
fun getStackTrace(throwable: Throwable): String {
    val stringWriter = StringWriter()
    val printWriter = PrintWriter(stringWriter, true)

    throwable.printStackTrace(printWriter)

    return stringWriter.buffer.toString()
}

/**
 * Get full path of PsiFile.
 */
fun getFileFullPath(project: Project, virtualFile: VirtualFile): String? {
    val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)
            ?: return null

    val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

    return projectRootVirtualFile.path + File.separator + virtualFileRelativePath
}

/**
 * Get runtime info files list from module.
 */
fun getModuleRuntimeInfoFiles(module: Module) = module.getUserData<List<String>>(MODULE_DATABASE_FILES_KEY)

/**
 * Check is module contains list of runtime-info files and current file path is
 * related to one of this runtime-info files.
 */
fun isRuntimeInfoDisabled(module: Module, fileFullPath: String): Boolean {
    val moduleRuntimeInfoFiles = getModuleRuntimeInfoFiles(module) ?: return true

    return if (moduleRuntimeInfoFiles.isEmpty()) {
        true
    } else {
        for (runtimeInfoFile in moduleRuntimeInfoFiles) {
            val absolutePath = File(runtimeInfoFile).parentFile.absolutePath ?: continue

            if (fileFullPath.startsWith(absolutePath)) {
                return false
            }
        }

        true
    }
}