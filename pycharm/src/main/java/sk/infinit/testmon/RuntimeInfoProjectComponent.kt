package sk.infinit.testmon

import com.intellij.ProjectTopics
import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.components.ServiceManager
import com.intellij.openapi.module.Module
import com.intellij.openapi.project.ModuleListener
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.*
import com.intellij.openapi.wm.ToolWindowManager
import sk.infinit.testmon.services.cache.Cache
import sk.infinit.testmon.toolWindow.RuntimeInfoListPanel
import com.intellij.openapi.roots.ModuleRootManager
import com.intellij.openapi.wm.ToolWindow


class RuntimeInfoProjectComponent(private val project: Project) : ProjectComponent {

    override fun getComponentName(): String {
        return "RuntimeInfoProjectComponent"
    }

    private lateinit var virtualFileListener: VirtualFileListener

    var databaseFiles: MutableSet<String>

    init {
        databaseFiles = getDatabaseFiles(project)?: HashSet()
        project.putUserData(PROJECT_USERDATA_KEY, databaseFiles)

    }

    override fun projectOpened() {
        val contentRoots = ProjectRootManager.getInstance(project).contentRoots

        for (contentRoot in contentRoots) {
            VfsUtilCore.iterateChildrenRecursively(contentRoot, null, {
                if (it.name == DATABASE_FILE_NAME) {
                    databaseFiles.add(it.path)
                }

                true
            })
        }

        virtualFileListener = buildDatabasesListener()

        VirtualFileManager.getInstance().addVirtualFileListener(virtualFileListener)

        project.messageBus.connect().subscribe(ProjectTopics.MODULES, buildModuleListener())
    }

    /**
     * This steps needed to prevent firing events on closed project(s).
     */
    override fun projectClosed() {
        VirtualFileManager.getInstance().removeVirtualFileListener(virtualFileListener)

        project.messageBus.connect().disconnect()
    }

    private fun buildDatabasesListener(): VirtualFileListener {
        return object : VirtualFileListener {
            override fun fileCreated(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val runtimeInfoFilePath = it.path

                        databaseFiles.add(runtimeInfoFilePath)

                        invalidateCache()

                        logInfoMessage("runtime-info file created: $runtimeInfoFilePath", project)

                        addRuntimeInfoFileToToolWindow(runtimeInfoFilePath)
                    }

                    true
                })
            }

            override fun beforeFileDeletion(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val runtimeInfoFilePath = it.path

                        databaseFiles.remove(runtimeInfoFilePath)

                        invalidateCache()

                        logInfoMessage("runtime-info file deleted: $runtimeInfoFilePath", project)

                        removeRuntimeInfoFileFromToolWindow(runtimeInfoFilePath)
                    }

                    true
                })
            }

            override fun contentsChanged(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {

                        val cacheService = ServiceManager.getService(project, Cache::class.java)

                        cacheService?.clear()
                    }

                    true
                })
            }
        }
    }

    private fun buildModuleListener(): ModuleListener {
        return object : ModuleListener {
            override fun moduleAdded(project: Project, module: Module) {
                val rootManager = ModuleRootManager.getInstance(module)

                for (rootVirtualFile in rootManager.contentRoots) {
                    VfsUtilCore.iterateChildrenRecursively(rootVirtualFile, null, {
                        if (it.name == DATABASE_FILE_NAME) {
                            val runtimeInfoFilePath = it.path

                            databaseFiles.add(runtimeInfoFilePath)

                            addRuntimeInfoFileToToolWindow(runtimeInfoFilePath)
                        }

                        true
                    })
                }
            }
        }
    }

    private fun invalidateCache() {

        val cacheService = ServiceManager.getService(project, Cache::class.java)

        cacheService?.clear()
    }

    private fun getToolWindow(): ToolWindow? {
        val toolWindowManager = ToolWindowManager.getInstance(project) ?: return null

        return toolWindowManager.getToolWindow("Runtime Info")
    }

    private fun getRuntimeInfoListPanel(): RuntimeInfoListPanel? {
        val runtimeInfoToolWindow = getToolWindow() ?: return null

        val content = runtimeInfoToolWindow.contentManager.getContent(0)
                ?: return null

        return content.component as RuntimeInfoListPanel
    }

    private fun addRuntimeInfoFileToToolWindow(runtimeInfoFile: String) {
        getRuntimeInfoListPanel()?.addFile(runtimeInfoFile)
    }

    private fun removeRuntimeInfoFileFromToolWindow(runtimeInfoFile: String) {
        getRuntimeInfoListPanel()?.removeFile(runtimeInfoFile)
    }
}