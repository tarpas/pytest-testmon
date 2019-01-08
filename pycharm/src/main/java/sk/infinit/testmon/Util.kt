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

const val DATABASE_FILE_NAME = ".runtime_info0"

val MODULE_DATABASE_FILES_KEY = Key.create<List<String>>(DATABASE_FILE_NAME)

fun logErrorMessage(exception: Exception, project: Project) {
    val message = if (exception.message != null) {
        exception.message
    } else {
        getStackTrace(exception)
    }

    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID,
            "Runtime-info plugin", message!!, NotificationType.ERROR), project)
}

fun logInfoMessage(message: String, project: Project) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID,
            "Runtime-info plugin", message, NotificationType.INFORMATION), project)
}

fun getVirtualFileRelativePath(virtualFile: VirtualFile, projectRootVirtualFile: VirtualFile): String?
        = VfsUtilCore.getRelativePath(virtualFile, projectRootVirtualFile)

fun getProjectRootDirectoryVirtualFile(project: Project, virtualFile: VirtualFile): VirtualFile?
        = ProjectFileIndex.SERVICE.getInstance(project).getContentRootForFile(virtualFile)

fun findVirtualFile(filePath: String?): VirtualFile? {
    return if (filePath != null) {
        VfsUtil.findFileByIoFile(File(filePath), false)
    } else {
        null
    }
}

fun getStackTrace(throwable: Throwable): String {
    val stringWriter = StringWriter()
    val printWriter = PrintWriter(stringWriter, true)

    throwable.printStackTrace(printWriter)

    return stringWriter.buffer.toString()
}

fun getFileFullPath(project: Project, virtualFile: VirtualFile): String? {
    val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)
            ?: return null

    val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

    return projectRootVirtualFile.path + File.separator + virtualFileRelativePath
}

fun getRuntimeInfoFiles(project: Project) = project.getUserData<List<String>>(MODULE_DATABASE_FILES_KEY)
