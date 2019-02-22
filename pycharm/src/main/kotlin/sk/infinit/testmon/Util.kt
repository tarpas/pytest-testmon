package sk.infinit.testmon

import com.intellij.notification.Notification
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.util.Key
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import sk.infinit.testmon.services.cache.Cache
import sk.infinit.testmon.services.cache.CacheService
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.lang.Exception

const val DATABASE_FILE_NAME = ".runtime_info0"

val PROJECT_USERDATA_KEY = Key.create<MutableSet<String>>("runtime-info")

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

fun getVirtualFileRelativePath(fileRootDirectoryPath: String, absolutePyFilePath: String): String {
    val file = File(absolutePyFilePath)
    return file.toRelativeString(File(fileRootDirectoryPath))
}

fun getDatabaseFiles(project: Project) = project.getUserData<MutableSet<String>>(PROJECT_USERDATA_KEY)
